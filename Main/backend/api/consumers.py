import json
import asyncio
import logging
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from datascraper.r2c_context_manager import R2CContextManager
from datascraper.models_config import MODELS_CONFIG
from datascraper import datascraper as ds
from datascraper import cdm_rag
import openai
import os

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    """处理聊天WebSocket连接"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.r2c_manager = R2CContextManager()
        self.current_page_info = None  # 当前页面信息（按需获取）
        self.stop_generation = False  # 停止生成标志

    async def connect(self):
        # 加入聊天组以接收页面信息
        await self.channel_layer.group_add("chat_clients", self.channel_name)
        await self.accept()
        logger.info(f"Chat WebSocket connected - Channel: {self.channel_name} - Added to chat_clients group")

    async def disconnect(self, close_code):
        # 离开聊天组
        await self.channel_layer.group_discard("chat_clients", self.channel_name)
        logger.info(f"Chat WebSocket disconnected: {close_code}")
        
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'set_session':
                await self.handle_set_session(data)
            elif message_type == 'stop_generation':
                await self.handle_stop_generation(data)
                
        except Exception as e:
            logger.error(f"Error in ChatConsumer.receive: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))
            
    async def handle_set_session(self, data):
        """设置会话ID"""
        self.session_id = data.get('session_id', 'default_session')
        await self.send(text_data=json.dumps({
            'type': 'session_set',
            'session_id': self.session_id
        }))

    async def handle_stop_generation(self, data):
        """处理停止生成请求"""
        # 设置停止标志
        self.stop_generation = True
        logger.info("Generation stop requested by user")

        await self.send(text_data=json.dumps({
            'type': 'generation_stopped',
            'message': 'Generation stopped by user request'
        }))

    async def handle_chat_message(self, data):
        """处理聊天消息"""
        # 重置停止标志
        self.stop_generation = False

        question = data.get('message', '')
        models = data.get('models', ['gpt-3.5-turbo'])
        use_rag = data.get('use_rag', False)
        use_agent = data.get('use_agent', False)  # 新增agent模式

        if not question:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Message is required'
            }))
            return

        # 发送状态：正在生成回复
        await self.send(text_data=json.dumps({
            'type': 'status',
            'message': 'Generating response...'
        }))

        try:
            if use_agent:
                # 使用Agent模式（MCP工具调用）
                await self.get_agent_response_stream(question, models)
            else:
                # 直接使用最新的页面信息（来自定时更新）
                # 获取AI响应（流式）
                await self.get_ai_response_stream(question, models, use_rag)

        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing request: {str(e)}'
            }))



    async def page_info_response(self, event):
        """接收页面信息响应"""
        page_info = {
            'url': event['url'],
            'content': event['content'],
            'title': event.get('title', ''),
            'session_id': event['session_id'],
            'timestamp': event.get('timestamp', None),
            'is_active': event.get('is_active', False)
        }

        # 添加到响应列表
        if not hasattr(self, 'page_responses'):
            self.page_responses = []
        self.page_responses.append(page_info)

        active_status = "🟢 ACTIVE" if page_info['is_active'] else "⚪ background"
        logger.info(f"Page info response received: {event['url'][:50]}... ({active_status})")

    async def page_info_update(self, event):
        """处理页面信息更新（定时更新）"""
        logger.info(f"ChatConsumer.page_info_update called with URL: {event.get('url', 'Unknown')}")

        page_info = {
            'url': event['url'],
            'content': event['content'],
            'title': event.get('title', ''),
            'session_id': event['session_id'],
            'timestamp': event.get('timestamp', None),
            'is_active': event.get('is_active', False)
        }

        # 更新或添加到页面响应列表
        if not hasattr(self, 'page_responses'):
            self.page_responses = []

        # 查找是否已存在相同URL的页面信息
        existing_index = -1
        for i, existing_page in enumerate(self.page_responses):
            if existing_page['url'] == page_info['url']:
                existing_index = i
                break

        if existing_index >= 0:
            # 更新现有页面信息
            self.page_responses[existing_index] = page_info
        else:
            # 添加新页面信息
            self.page_responses.append(page_info)

        active_status = "🟢 ACTIVE" if page_info['is_active'] else "⚪ background"
        logger.info(f"Page info updated: {event['url'][:50]}... ({active_status})")

    async def page_navigation_signal(self, event):
        """处理页面导航信号"""
        url = event['url']
        title = event.get('title', '')
        session_id = event['session_id']
        timestamp = event.get('timestamp', None)

        logger.info(f"Received page navigation signal: {url}")

        # 清除旧的页面信息，为新页面做准备
        if hasattr(self, 'page_responses'):
            old_count = len(self.page_responses)
            self.page_responses = []
            logger.info(f"Cleared {old_count} old page responses due to navigation to {url}")

    def get_active_page_info(self):
        """获取当前活跃页面信息"""
        if not hasattr(self, 'page_responses') or not self.page_responses:
            return None

        # 优先选择active页面
        active_pages = [page for page in self.page_responses if page.get('is_active', False)]
        if active_pages:
            # 如果有多个active页面，选择最新的
            return max(active_pages, key=lambda x: x.get('timestamp', 0))

        # 如果没有active页面，选择最新的响应
        return max(self.page_responses, key=lambda x: x.get('timestamp', 0))

    async def get_ai_response_stream(self, question, models, use_rag):
        """获取AI响应（流式）"""
        try:
            session_id = self.session_id or 'default_session'

            # 准备上下文
            context_messages = await database_sync_to_async(self.r2c_manager.prepare_context_messages)(session_id)

            # 构建页面上下文（使用最新的定时更新数据）
            enhanced_question = question
            active_page = self.get_active_page_info()
            logger.info(f"Available page responses: {len(getattr(self, 'page_responses', []))}")
            if active_page and active_page['content']:
                page_context = f"""
Current Page Information:
Title: {active_page.get('title', 'Unknown Title')}
URL: {active_page['url']}
Page Content: {active_page['content'][:2000]}...

User Question: {question}
"""
                enhanced_question = page_context
                logger.info(f"Using active page context: {active_page.get('title', 'Unknown')}")
            else:
                logger.info("No active page info available, using question only")

            # 添加用户消息到R2C上下文
            await database_sync_to_async(self.r2c_manager.add_message)(session_id, "user", enhanced_question)

            # 选择模型
            model_name = models[0] if models else 'deepseek-chat'
            model_config = MODELS_CONFIG.get(model_name)

            if not model_config:
                raise ValueError(f"Model {model_name} not found in configuration")

            # 获取提供商配置
            from datascraper.models_config import PROVIDER_CONFIGS
            provider = model_config['provider']
            provider_config = PROVIDER_CONFIGS[provider]

            # 获取API密钥
            api_key = os.getenv(provider_config['env_key'])
            if not api_key:
                raise ValueError(f"API key not found for provider {provider}")

            # 构建消息
            messages = context_messages + [{"role": "user", "content": enhanced_question}]

            # 发送流式响应开始标记
            await self.send(text_data=json.dumps({
                'type': 'stream_start',
                'model': model_name
            }))

            if use_rag:
                # RAG模式暂时不支持流式，直接返回结果
                rag_response = await database_sync_to_async(cdm_rag.get_rag_response)(question, model_name)
                await self.send(text_data=json.dumps({
                    'type': 'stream_content',
                    'content': rag_response
                }))
                full_response = rag_response
            else:
                # 流式调用模型
                import openai
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=provider_config.get('base_url')
                )

                full_response = ""
                stream = client.chat.completions.create(
                    model=model_config['model_name'],
                    messages=messages,
                    max_tokens=model_config.get('max_tokens', 2000),
                    temperature=model_config.get('temperature', 0.7),
                    stream=True
                )

                import asyncio
                for chunk in stream:
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content is not None:
                            content = delta.content
                            full_response += content

                            # 发送流式内容
                            await self.send(text_data=json.dumps({
                                'type': 'stream_content',
                                'content': content
                            }))

                            # 添加小延迟确保真正的流式传输
                            await asyncio.sleep(0.002)  # 2毫秒延迟

            # 发送流式响应结束标记
            await self.send(text_data=json.dumps({
                'type': 'stream_end'
            }))

            # 添加AI响应到R2C上下文
            await database_sync_to_async(self.r2c_manager.add_message)(session_id, "assistant", full_response)

            # 获取R2C统计信息
            r2c_stats = await database_sync_to_async(self.r2c_manager.get_session_stats)(session_id)

            # 发送最终响应信息
            await self.send(text_data=json.dumps({
                'type': 'response_complete',
                'model': model_name,
                'r2c_stats': r2c_stats
            }))

        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error getting AI response: {str(e)}'
            }))

    @database_sync_to_async
    def get_ai_response(self, question, models, use_rag):
        """获取AI响应（同步转异步）"""
        try:
            session_id = self.session_id or 'default_session'
            
            # 准备上下文
            context_messages = self.r2c_manager.prepare_context_messages(session_id)

            # 构建页面上下文
            enhanced_question = question
            if self.current_page_info and self.current_page_info['content']:
                page_context = f"""
Current page information：
Title: {self.current_page_info.get('title', 'unknown')}
URL: {self.current_page_info['url']}
COntent: {self.current_page_info['content'][:2000]}...

User question: {question}
"""
                enhanced_question = page_context
                logger.info(f"Added page context: {self.current_page_info.get('title', 'Unknown')}")

            # 添加用户消息
            self.r2c_manager.add_message(session_id, "user", enhanced_question)
            
            # 选择模型
            model_name = models[0] if models else 'deepseek-chat'
            model_config = MODELS_CONFIG.get(model_name)

            if not model_config:
                raise ValueError(f"Model {model_name} not found in configuration")

            # 获取提供商配置
            from datascraper.models_config import PROVIDER_CONFIGS
            provider = model_config['provider']
            provider_config = PROVIDER_CONFIGS[provider]

            # 获取API密钥
            api_key = os.getenv(provider_config['env_key'])
            if not api_key:
                raise ValueError(f"API key not found for provider {provider}")

            # 构建消息
            messages = context_messages + [{"role": "user", "content": enhanced_question}]

            if use_rag:
                # 使用RAG
                rag_response = cdm_rag.get_rag_response(question, model_name)
                response_text = rag_response
            else:
                # 直接调用模型
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=provider_config.get('base_url')
                )
                
                response = client.chat.completions.create(
                    model=model_config['model_name'],
                    messages=messages,
                    max_tokens=model_config.get('max_tokens', 2000),
                    temperature=model_config.get('temperature', 0.7)
                )
                
                response_text = response.choices[0].message.content
            
            # 添加助手响应
            self.r2c_manager.add_message(session_id, "assistant", response_text)
            
            # 获取R2C统计
            r2c_stats = self.r2c_manager.get_session_stats(session_id)
            
            return {
                'response': response_text,
                'model': model_name,
                'r2c_stats': r2c_stats
            }
            
        except Exception as e:
            logger.error(f"Error in get_ai_response: {e}")
            raise

    async def get_agent_response_stream(self, question, models):
        """获取Agent响应（流式，支持内置工具调用）"""
        try:
            session_id = self.session_id or 'default_session'

            # 准备上下文
            context_messages = await database_sync_to_async(self.r2c_manager.prepare_context_messages)(session_id)

            # 构建页面上下文（使用最新的定时更新数据）
            enhanced_question = question
            active_page = self.get_active_page_info()
            if active_page and active_page['content']:
                page_context = f"""
Current Page Information:
Title: {active_page.get('title', 'Unknown Title')}
URL: {active_page['url']}
Page Content: {active_page['content'][:2000]}...

User Question: {question}
"""
                enhanced_question = page_context
                logger.info(f"Using active page context: {active_page.get('title', 'Unknown')}")

            # 添加用户消息到R2C上下文
            await database_sync_to_async(self.r2c_manager.add_message)(session_id, "user", enhanced_question)

            # 选择模型
            model_name = models[0] if models else 'deepseek-chat'

            # 发送流式响应开始标记
            await self.send(text_data=json.dumps({
                'type': 'stream_start',
                'model': model_name
            }))

            # 使用内置工具系统
            from .builtin_tools import builtin_tool_manager

            # 构建Agent提示词
            tool_definitions = builtin_tool_manager.get_tool_definitions()
            agent_prompt = f"""
You are a helpful financial assistant with access to browser automation tools.

{tool_definitions}

Context from previous conversation:
{chr(10).join([f"{msg['role']}: {msg['content']}" for msg in context_messages[-3:]])}

Current request: {enhanced_question}

Instructions:
1. Analyze the user's request carefully
2. If the request involves web browsing, navigation, or browser interaction, use the appropriate tools
3. Use the exact tool call format specified above
4. After completing all necessary tool calls, provide a comprehensive summary of what was accomplished
5. Always end with a final response that answers the user's original question
"""

            # 显示工具分析状态
            await self.send(text_data=json.dumps({
                'type': 'tool_calling',
                'message': 'Analyzing request and selecting appropriate tools...'
            }))

            full_response = ""

            # 使用内置工具系统进行多轮对话 - 完全后台执行避免阻塞
            asyncio.create_task(
                self.run_builtin_agent_conversation_background(agent_prompt, enhanced_question, model_name)
            )

            # 立即返回，不等待agent完成
            return

            # 注意：流式响应结束标记和R2C上下文更新现在在后台方法中处理

            # 发送最终响应信息
            await self.send(text_data=json.dumps({
                'type': 'response_complete',
                'model': model_name,
                'r2c_stats': r2c_stats
            }))

        except Exception as e:
            logger.error(f"Error getting Agent response: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error getting Agent response: {str(e)}'
            }))

    async def run_builtin_agent_conversation_background(self, system_prompt, user_question, model_name):
        """后台运行Agent对话，不阻塞消息处理"""
        try:
            full_response = await self.run_builtin_agent_conversation(system_prompt, user_question, model_name)

            # 发送流式响应结束标记
            await self.send(text_data=json.dumps({
                'type': 'stream_end'
            }))

            # 添加AI响应到R2C上下文
            session_id = self.scope.get('session', {}).get('session_key', 'default_session')
            await database_sync_to_async(self.r2c_manager.add_message)(session_id, "assistant", full_response)

        except Exception as e:
            logger.error(f"Error in background agent conversation: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error getting Agent response: {str(e)}'
            }))

    async def run_builtin_agent_conversation(self, system_prompt, user_question, model_name):
        """使用内置工具系统运行Agent对话"""
        from .builtin_tools import builtin_tool_manager
        from datascraper.models_config import get_model_config

        try:
            # 获取模型配置
            from datascraper.models_config import get_model_config, PROVIDER_CONFIGS
            model_config = get_model_config(model_name)
            if not model_config:
                raise ValueError(f"Model {model_name} not found")

            # 获取提供商配置
            provider = model_config['provider']
            provider_config = PROVIDER_CONFIGS[provider]

            # 获取API密钥
            api_key = os.getenv(provider_config['env_key'])
            if not api_key:
                raise ValueError(f"API key not found for provider {provider}")

            max_iterations = 5  # 最大工具调用轮数
            conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ]

            for iteration in range(max_iterations):
                # 检查是否需要停止生成
                if self.stop_generation:
                    logger.info("Generation stopped by user request")
                    self.stop_generation = False  # 重置标志
                    return "Generation stopped by user."

                logger.info(f"Agent iteration {iteration + 1}/{max_iterations}")

                # 让出控制权，允许处理其他消息（如页面信息更新）
                await asyncio.sleep(0)

                # 调用AI模型 - 使用现有的流式响应逻辑
                import openai
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=provider_config.get('base_url')
                )

                response_text = ""
                stream = client.chat.completions.create(
                    model=model_config['model_name'],
                    messages=conversation_history,
                    max_tokens=model_config.get('max_tokens', 2000),
                    temperature=model_config.get('temperature', 0.7),
                    stream=True
                )

                for chunk in stream:
                    # 检查是否需要停止生成
                    if self.stop_generation:
                        logger.info("Generation stopped during streaming")
                        self.stop_generation = False  # 重置标志
                        return "Generation stopped by user."

                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content is not None:
                            content = delta.content
                            response_text += content

                            # 暂时不发送流式响应，等确定没有工具调用时再发送
                            # 添加小延迟确保真正的流式传输
                            await asyncio.sleep(0.002)  # 2毫秒延迟

                # 解析工具调用
                tool_calls = builtin_tool_manager.parse_tool_calls(response_text)

                if not tool_calls:
                    # 没有工具调用，对话结束 - 现在进行流式传输
                    logger.info("No tool calls found, streaming final response")

                    # 发送流式响应
                    for char in response_text:
                        await self.send(text_data=json.dumps({
                            'type': 'stream_chunk',
                            'content': char
                        }))
                        await asyncio.sleep(0.01)  # 10毫秒延迟，让流式效果更明显

                    return response_text

                # 执行工具调用
                conversation_history.append({"role": "assistant", "content": response_text})

                for tool_call in tool_calls:
                    # 检查是否需要停止生成
                    if self.stop_generation:
                        logger.info("Generation stopped before tool execution")
                        self.stop_generation = False  # 重置标志
                        return "Generation stopped by user."

                    tool_name = tool_call['tool']
                    parameters = tool_call['parameters']

                    # 显示工具调用状态
                    await self.send(text_data=json.dumps({
                        'type': 'tool_calling',
                        'message': f'Calling Tool: {tool_name}',
                        'tool_details': {
                            'tool_name': tool_name,
                            'parameters': parameters,
                            'timestamp': time.time()
                        }
                    }))

                    # 执行工具
                    tool_result = await builtin_tool_manager.execute_tool(
                        tool_name, parameters, self
                    )

                    # 让出控制权，允许处理其他消息
                    await asyncio.sleep(0)

                    # 检查是否在工具执行后需要停止
                    if self.stop_generation:
                        logger.info("Generation stopped after tool execution")
                        self.stop_generation = False  # 重置标志
                        return "Generation stopped by user."

                    # 显示工具完成状态
                    if tool_result['success']:
                        await self.send(text_data=json.dumps({
                            'type': 'tool_result',
                            'message': f'Tool execution completed successfully',
                            'tool_details': {
                                'tool_name': tool_name,
                                'parameters': parameters,
                                'result': tool_result['result'],
                                'timestamp': time.time()
                            }
                        }))
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'tool_result',
                            'message': f'Tool execution failed: {tool_result["error"]}',
                            'tool_details': {
                                'tool_name': tool_name,
                                'parameters': parameters,
                                'error': tool_result.get('error', 'Unknown error'),
                                'timestamp': time.time()
                            }
                        }))

                    # 将工具结果添加到对话历史
                    tool_result_message = f"Tool '{tool_name}' result: {json.dumps(tool_result, indent=2)}"
                    conversation_history.append({"role": "user", "content": tool_result_message})

            # 如果达到最大迭代次数，强制AI给出最终总结
            logger.warning(f"Reached maximum iterations ({max_iterations}), requesting final summary")

            # 添加总结请求
            conversation_history.append({
                "role": "user",
                "content": "Please provide a comprehensive summary of what you accomplished and answer the original question."
            })

            # 获取最终总结
            final_response = ""
            stream = client.chat.completions.create(
                model=model_config['model_name'],
                messages=conversation_history,
                max_tokens=model_config.get('max_tokens', 2000),
                temperature=model_config.get('temperature', 0.7),
                stream=True
            )

            for chunk in stream:
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content is not None:
                        content = delta.content
                        final_response += content

                        # 实时发送响应流
                        await self.send(text_data=json.dumps({
                            'type': 'stream_chunk',
                            'content': content
                        }))

                        await asyncio.sleep(0.002)

            return final_response

        except Exception as e:
            logger.error(f"Error in builtin agent conversation: {e}")
            raise

    async def send_to_extension(self, message):
        """向Chrome插件发送消息（通过WebSocket）"""
        try:
            # 这里可以实现向Chrome插件发送消息的逻辑
            # 目前先记录日志，后续可以扩展
            logger.info(f"Would send to extension: {message}")

            # 如果有连接的Chrome插件，可以通过channel layer发送消息
            # 这需要Chrome插件也连接到WebSocket

        except Exception as e:
            logger.error(f"Error sending message to extension: {e}")


class BrowserControlConsumer(AsyncWebsocketConsumer):
    """处理浏览器控制WebSocket连接 - 用于Chrome插件接收操作命令"""

    # 类变量用于存储页面信息响应
    _page_info_responses = {}
    _page_info_events = {}

    async def connect(self):
        await self.accept()
        logger.info("Browser Control WebSocket connected")

        # 将此连接存储为全局浏览器控制连接
        # 这样其他consumer可以向浏览器发送命令
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        await channel_layer.group_add("browser_control", self.channel_name)

    async def disconnect(self, close_code):
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        await channel_layer.group_discard("browser_control", self.channel_name)
        logger.info(f"Browser Control WebSocket disconnected: {close_code}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            # 处理来自Chrome插件的响应消息
            if message_type.endswith('_result'):
                logger.info(f"Received browser operation result: {data}")

                # 特别处理页面信息响应
                if message_type == 'browser_info_result':
                    page_info = data.get('pageInfo', {})
                    request_id = data.get('request_id', 'default')

                    # 存储页面信息
                    BrowserControlConsumer._page_info_responses[request_id] = page_info

                    # 触发等待的事件
                    if request_id in BrowserControlConsumer._page_info_events:
                        BrowserControlConsumer._page_info_events[request_id].set()

                    logger.info(f"Stored page info for request {request_id}: {page_info.get('title', 'No title')}")

        except Exception as e:
            logger.error(f"Error in BrowserControlConsumer.receive: {e}")

    # 发送浏览器操作命令到Chrome插件
    async def browser_command(self, event):
        await self.send(text_data=json.dumps(event['data']))

    @classmethod
    async def wait_for_page_info(cls, request_id='default', timeout=10):
        """等待页面信息响应"""
        import asyncio

        # 创建事件
        event = asyncio.Event()
        cls._page_info_events[request_id] = event

        try:
            # 等待响应
            await asyncio.wait_for(event.wait(), timeout=timeout)

            # 获取响应数据
            page_info = cls._page_info_responses.get(request_id, {})

            # 清理
            cls._page_info_responses.pop(request_id, None)
            cls._page_info_events.pop(request_id, None)

            return page_info

        except asyncio.TimeoutError:
            # 清理
            cls._page_info_events.pop(request_id, None)
            logger.warning(f"Timeout waiting for page info response: {request_id}")
            return None


class PageInfoConsumer(AsyncWebsocketConsumer):
    """处理页面信息WebSocket连接"""
    
    async def connect(self):
        # 加入页面信息组
        await self.channel_layer.group_add("page_info", self.channel_name)
        await self.accept()
        logger.info("PageInfo WebSocket connected")
        
    async def disconnect(self, close_code):
        # 离开页面信息组
        await self.channel_layer.group_discard("page_info", self.channel_name)
        logger.info(f"PageInfo WebSocket disconnected: {close_code}")
        
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'page_update':
                await self.handle_page_update(data)
            elif message_type == 'page_info_response':
                await self.handle_page_info_response(data)
            elif message_type == 'page_navigation':
                await self.handle_page_navigation(data)

        except Exception as e:
            logger.error(f"Error in PageInfoConsumer.receive: {e}")

    async def handle_page_navigation(self, data):
        """处理页面导航信号"""
        url = data.get('url', '')
        title = data.get('title', '')
        session_id = data.get('session_id', 'default_session')
        timestamp = data.get('timestamp', None)

        logger.info(f"Page navigation detected: {url}")

        # 广播页面导航信号到聊天消费者，让它们清除旧的页面信息
        await self.channel_layer.group_send("chat_clients", {
            'type': 'page_navigation_signal',
            'url': url,
            'title': title,
            'session_id': session_id,
            'timestamp': timestamp
        })

    async def handle_page_update(self, data):
        """处理页面更新"""
        url = data.get('url', '')
        content = data.get('content', '')
        title = data.get('title', '')
        session_id = data.get('session_id', 'default_session')
        timestamp = data.get('timestamp', None)
        is_active = data.get('is_active', False)

        # 广播页面信息到聊天消费者
        logger.info(f"PageInfoConsumer: Broadcasting page_info_update to chat_clients group - URL: {url[:50]}...")
        await self.channel_layer.group_send("chat_clients", {
            'type': 'page_info_update',
            'url': url,
            'content': content,
            'title': title,
            'session_id': session_id,
            'timestamp': timestamp,
            'is_active': is_active
        })
        logger.info(f"PageInfoConsumer: page_info_update message sent to chat_clients group")

        # 也广播到页面信息组（用于调试）
        await self.channel_layer.group_send("page_info", {
            'type': 'page_info_update',
            'url': url,
            'content': content,
            'title': title,
            'session_id': session_id,
            'timestamp': timestamp,
            'is_active': is_active
        })

        status = "active" if is_active else "background"
        logger.info(f"Page info updated and broadcasted ({status}): {url[:50]}...")

    async def handle_page_info_response(self, data):
        """处理页面信息响应"""
        # 转发页面信息响应到聊天消费者
        await self.channel_layer.group_send("chat_clients", {
            'type': 'page_info_response',
            'url': data.get('url', ''),
            'content': data.get('content', ''),
            'title': data.get('title', ''),
            'session_id': data.get('session_id', 'default_session'),
            'timestamp': data.get('timestamp', None),
            'is_active': data.get('is_active', False)
        })

    async def request_page_info(self, event):
        """请求页面信息"""
        logger.info("PageInfoConsumer: Sending request_page_info to content script")
        await self.send(text_data=json.dumps({
            'type': 'request_page_info'
        }))
        logger.info("PageInfoConsumer: request_page_info message sent")

    async def page_info_update(self, event):
        """接收页面信息更新（保留用于调试）"""
        await self.send(text_data=json.dumps({
            'type': 'page_info',
            'url': event['url'],
            'content': event['content'],
            'title': event.get('title', ''),
            'session_id': event['session_id'],
            'is_active': event.get('is_active', False)
        }))
