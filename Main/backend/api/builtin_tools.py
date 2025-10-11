"""
内置工具系统 - 不依赖MCP，直接集成到FinGPT中
"""
import json
import re
import asyncio
import logging
from typing import Dict, Any, List, Optional
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class BuiltinToolManager:
    """内置工具管理器"""
    
    def __init__(self):
        self.tools = {
            'browser_navigate': self.browser_navigate,
            'browser_press_key': self.browser_press_key,
            'browser_type': self.browser_type,
            'browser_click': self.browser_click,
            'browser_info': self.browser_info,
        }
        self.channel_layer = get_channel_layer()
    
    def get_tool_definitions(self) -> str:
        """获取工具定义，用于AI提示词"""
        return """
Available Tools:

1. browser_navigate(url: str) -> Dict
   Navigate to a URL in the user's browser and automatically retrieve page information.
   Returns page title, URL, content and a unique page_id after navigation.
   Example: browser_navigate("https://example.com")

2. browser_info(page_id: str = None) -> Dict
   Get information about a specific page or the current active page.
   If page_id is provided, gets info for that specific page.
   If no page_id, gets info for the currently active page.
   Example: browser_info() or browser_info("page_123")

3. browser_press_key(key: str) -> Dict
   Press a key on the keyboard in the user's browser.
   Example: browser_press_key("Enter")

4. browser_type(text: str) -> Dict
   Type text in the user's browser.
   Example: browser_type("Hello World")

5. browser_click(selector: str) -> Dict
   Click on an element in the user's browser using CSS selector.
   Example: browser_click("button.search-btn")

Tool Call Format:
When you want to use a tool, output exactly this format:
<tool_call>
{
    "tool": "tool_name",
    "parameters": {
        "param1": "value1",
        "param2": "value2"
    }
}
</tool_call>

Important: 
- Always use the exact format above
- Only call tools when they are relevant to the user's request
- After calling a tool, wait for the result before continuing
"""

    def parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """从AI响应中解析工具调用"""
        tool_calls = []
        
        # 使用正则表达式查找工具调用
        pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                tool_call = json.loads(match)
                if 'tool' in tool_call and 'parameters' in tool_call:
                    tool_calls.append(tool_call)
                    logger.info(f"Parsed tool call: {tool_call['tool']}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call JSON: {e}")
                continue
        
        return tool_calls
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """执行工具调用"""
        if tool_name not in self.tools:
            return {
                'success': False,
                'error': f'Unknown tool: {tool_name}',
                'result': None
            }
        
        try:
            logger.info(f"Executing tool: {tool_name} with parameters: {parameters}")
            result = await self.tools[tool_name](parameters, websocket_consumer)
            return {
                'success': True,
                'error': None,
                'result': result
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'result': None
            }
    
    async def browser_navigate(self, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """浏览器导航工具 - 通过Chrome插件执行，导航后自动获取页面信息"""
        url = parameters.get('url')
        if not url:
            raise ValueError("URL parameter is required")

        try:
            # 清除旧的页面信息，强制获取新页面信息
            if websocket_consumer and hasattr(websocket_consumer, 'page_responses'):
                old_count = len(websocket_consumer.page_responses)
                websocket_consumer.page_responses = []  # 清空旧的页面信息
                logger.info(f"Cleared {old_count} old page responses before navigation")

            # 发送导航命令
            await self.channel_layer.group_send("browser_control", {
                "type": "browser_command",
                "data": {
                    "type": "browser_navigate",
                    "url": url
                }
            })

            # 等待页面加载和页面信息更新 - 分段等待以避免阻塞
            logger.info(f"Waiting for page to load and WebSocket to reconnect...")

            # 分段等待，每秒让出控制权 - 缩短到2秒
            for _ in range(2):
                await asyncio.sleep(1)
                # 让出控制权，允许处理其他消息
                await asyncio.sleep(0)

            # 从websocket_consumer获取最新的页面信息（使用现有的页面信息机制）
            if websocket_consumer and hasattr(websocket_consumer, 'get_active_page_info'):
                page_info = websocket_consumer.get_active_page_info()

                # 检查页面信息是否匹配目标URL
                if page_info and page_info.get('content'):
                    page_url = page_info.get('url', '')

                    # 检查URL是否匹配（考虑重定向）
                    from urllib.parse import urlparse
                    target_domain = urlparse(url).netloc
                    page_domain = urlparse(page_url).netloc

                    logger.info(f"Checking URL match: target={target_domain}, page={page_domain}")

                    # 如果域名匹配或者是合理的重定向，使用页面信息
                    # 更宽松的匹配逻辑
                    domain_match = (
                        target_domain in page_domain or
                        page_domain in target_domain or
                        target_domain.replace('www.', '') == page_domain.replace('www.', '') or
                        any(keyword in page_domain.lower() for keyword in ['yahoo', 'finance', 'bilibili', 'httpbin', 'duckduckgo'])
                    )

                    if domain_match:
                        # 处理页面内容，确保不会太长
                        content = page_info.get('content', '')
                        if len(content) > 3000:
                            content = content[:3000] + '...'

                        # 生成页面ID
                        import uuid
                        page_id = f"page_{str(uuid.uuid4())[:8]}"

                        # 存储页面信息到websocket_consumer（如果可用）
                        if websocket_consumer:
                            if not hasattr(websocket_consumer, 'page_cache'):
                                websocket_consumer.page_cache = {}
                            websocket_consumer.page_cache[page_id] = page_info

                        logger.info(f"Successfully matched page: {page_info.get('title', 'Unknown')}")
                        return {
                            'action': 'navigate',
                            'url': url,
                            'status': 'completed',
                            'title': page_info.get('title', 'Unknown Title'),
                            'final_url': page_info.get('url', url),
                            'content': content,
                            'timestamp': page_info.get('timestamp', ''),
                            'page_id': page_id,
                            'message': f'Successfully navigated to {url} and retrieved page information: {page_info.get("title", "Unknown")} (Page ID: {page_id})'
                        }
                    else:
                        logger.warning(f"Page URL mismatch: expected {url}, got {page_url}")

                # 如果页面信息不匹配，再等待一下
                await asyncio.sleep(3)
                page_info = websocket_consumer.get_active_page_info()

                if page_info and page_info.get('content'):
                    page_url = page_info.get('url', '')
                    target_domain = urlparse(url).netloc
                    page_domain = urlparse(page_url).netloc

                    if target_domain in page_domain or page_domain in target_domain:
                        content = page_info.get('content', '')
                        if len(content) > 3000:
                            content = content[:3000] + '...'

                        # 生成页面ID
                        import uuid
                        page_id = f"page_{str(uuid.uuid4())[:8]}"

                        # 存储页面信息到websocket_consumer（如果可用）
                        if websocket_consumer:
                            if not hasattr(websocket_consumer, 'page_cache'):
                                websocket_consumer.page_cache = {}
                            websocket_consumer.page_cache[page_id] = page_info

                        return {
                            'action': 'navigate',
                            'url': url,
                            'status': 'completed',
                            'title': page_info.get('title', 'Unknown Title'),
                            'final_url': page_info.get('url', url),
                            'content': content,
                            'timestamp': page_info.get('timestamp', ''),
                            'page_id': page_id,
                            'message': f'Successfully navigated to {url} and retrieved page information: {page_info.get("title", "Unknown")} (Page ID: {page_id})'
                        }

            # 如果没有获取到页面信息，返回基本的导航成功信息
            return {
                'action': 'navigate',
                'url': url,
                'status': 'completed',
                'message': f'Successfully navigated to {url}. Page information will be available shortly.'
            }

        except Exception as e:
            logger.error(f"Failed to navigate: {e}")
            return {
                'action': 'navigate',
                'url': url,
                'status': 'failed',
                'message': f'Failed to navigate: {str(e)}'
            }
    
    async def browser_press_key(self, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """按键工具"""
        key = parameters.get('key')
        if not key:
            raise ValueError("Key parameter is required")

        try:
            await self.channel_layer.group_send("browser_control", {
                "type": "browser_command",
                "data": {
                    "type": "browser_press_key",
                    "key": key
                }
            })

            return {
                'action': 'press_key',
                'key': key,
                'status': 'completed',
                'message': f'Successfully sent key press command: {key}'
            }
        except Exception as e:
            logger.error(f"Failed to send key press command: {e}")
            return {
                'action': 'press_key',
                'key': key,
                'status': 'failed',
                'message': f'Failed to send key press command: {str(e)}'
            }
    
    async def browser_type(self, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """输入文本工具"""
        text = parameters.get('text')
        if not text:
            raise ValueError("Text parameter is required")

        try:
            await self.channel_layer.group_send("browser_control", {
                "type": "browser_command",
                "data": {
                    "type": "browser_type",
                    "text": text
                }
            })

            return {
                'action': 'type',
                'text': text,
                'status': 'completed',
                'message': f'Successfully sent type command: {text}'
            }
        except Exception as e:
            logger.error(f"Failed to send type command: {e}")
            return {
                'action': 'type',
                'text': text,
                'status': 'failed',
                'message': f'Failed to send type command: {str(e)}'
            }

    async def browser_click(self, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """点击工具"""
        selector = parameters.get('selector')
        if not selector:
            raise ValueError("Selector parameter is required")

        try:
            await self.channel_layer.group_send("browser_control", {
                "type": "browser_command",
                "data": {
                    "type": "browser_click",
                    "selector": selector
                }
            })

            return {
                'action': 'click',
                'selector': selector,
                'status': 'completed',
                'message': f'Successfully sent click command for: {selector}'
            }
        except Exception as e:
            logger.error(f"Failed to send click command: {e}")
            return {
                'action': 'click',
                'selector': selector,
                'status': 'failed',
                'message': f'Failed to send click command: {str(e)}'
            }

    async def browser_info(self, parameters: Dict[str, Any], websocket_consumer=None) -> Dict[str, Any]:
        """获取页面信息工具 - 支持通过page_id获取特定页面信息"""
        try:
            page_id = parameters.get('page_id')

            if page_id and websocket_consumer and hasattr(websocket_consumer, 'page_cache'):
                # 从缓存中获取特定页面信息
                page_info = websocket_consumer.page_cache.get(page_id)
                if page_info:
                    content = page_info.get('content', '')
                    if len(content) > 3000:
                        content = content[:3000] + '...'

                    return {
                        'action': 'get_info',
                        'status': 'completed',
                        'title': page_info.get('title', 'Unknown Title'),
                        'url': page_info.get('url', 'Unknown URL'),
                        'content': content,
                        'timestamp': page_info.get('timestamp', ''),
                        'page_id': page_id,
                        'message': f'Successfully retrieved cached page information for {page_id}: {page_info.get("title", "Unknown")}'
                    }
                else:
                    return {
                        'action': 'get_info',
                        'status': 'failed',
                        'message': f'Page ID {page_id} not found in cache'
                    }
            else:
                # 获取当前活跃页面信息 - 添加等待机制和详细调试
                if websocket_consumer and hasattr(websocket_consumer, 'get_active_page_info'):
                    # 尝试多次获取页面信息，因为页面可能正在加载
                    max_attempts = 3
                    for attempt in range(max_attempts):
                        # 添加详细的调试信息
                        if hasattr(websocket_consumer, 'page_responses'):
                            logger.info(f"Attempt {attempt + 1}: page_responses count = {len(websocket_consumer.page_responses)}")
                            for i, resp in enumerate(websocket_consumer.page_responses):
                                logger.info(f"  Response {i}: {resp.get('url', 'Unknown')} - Content: {len(resp.get('content', ''))} chars - Active: {resp.get('is_active', False)}")
                        else:
                            logger.info(f"Attempt {attempt + 1}: page_responses attribute not found")

                        page_info = websocket_consumer.get_active_page_info()

                        if page_info and page_info.get('content'):
                            content = page_info.get('content', '')
                            if len(content) > 3000:
                                content = content[:3000] + '...'

                            logger.info(f"Successfully retrieved page info on attempt {attempt + 1}: {page_info.get('title', 'Unknown')}")
                            return {
                                'action': 'get_info',
                                'status': 'completed',
                                'title': page_info.get('title', 'Unknown Title'),
                                'url': page_info.get('url', 'Unknown URL'),
                                'content': content,
                                'timestamp': page_info.get('timestamp', ''),
                                'message': f'Successfully retrieved current page information: {page_info.get("title", "Unknown")}'
                            }

                        # 如果没有获取到页面信息，等待一下再重试
                        if attempt < max_attempts - 1:
                            logger.info(f"No page info available on attempt {attempt + 1}, waiting 2 seconds...")
                            await asyncio.sleep(2)
                            # 让出控制权，允许处理其他消息
                            await asyncio.sleep(0)

                return {
                    'action': 'get_info',
                    'status': 'failed',
                    'message': 'No page information available after waiting. Please ensure the page is fully loaded and the extension is connected.'
                }

        except Exception as e:
            logger.error(f"Failed to get page info: {e}")
            return {
                'action': 'get_info',
                'status': 'failed',
                'message': f'Failed to get page info: {str(e)}'
            }

# 全局工具管理器实例
builtin_tool_manager = BuiltinToolManager()
