import json
import asyncio
import logging
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

    async def connect(self):
        # 加入聊天组以接收页面信息
        await self.channel_layer.group_add("chat_clients", self.channel_name)
        await self.accept()
        logger.info("Chat WebSocket connected")

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
        
    async def handle_chat_message(self, data):
        """处理聊天消息"""
        question = data.get('message', '')
        models = data.get('models', ['gpt-3.5-turbo'])
        use_rag = data.get('use_rag', False)

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

        except Exception as e:
            logger.error(f"Error in PageInfoConsumer.receive: {e}")
            
    async def handle_page_update(self, data):
        """处理页面更新"""
        url = data.get('url', '')
        content = data.get('content', '')
        title = data.get('title', '')
        session_id = data.get('session_id', 'default_session')
        timestamp = data.get('timestamp', None)
        is_active = data.get('is_active', False)

        # 广播页面信息到聊天消费者
        await self.channel_layer.group_send("chat_clients", {
            'type': 'page_info_update',
            'url': url,
            'content': content,
            'title': title,
            'session_id': session_id,
            'timestamp': timestamp,
            'is_active': is_active
        })

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
