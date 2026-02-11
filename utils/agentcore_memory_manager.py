"""
AgentCore Memory Manager for Customer Support System

This module provides AWS AgentCore-based memory management with DynamoDB session storage.
"""

import logging
import os
import json
import boto3
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)

class AgentCoreMemoryManager:
    """Manages memory sessions using AWS Bedrock AgentCore with DynamoDB"""
    
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.memory_client = None
        self.memory_id = None
        self.initialized = False
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.session_table_name = 'customer-support-sessions'
        self.session_table = None
        
        self._initialize_agentcore()
        self._ensure_session_table_exists()
    
    def _initialize_agentcore(self):
        """Initialize AWS AgentCore memory client"""
        try:
            from bedrock_agentcore.memory import MemoryClient
            
            self.memory_client = MemoryClient(region_name=self.region)
            
            # Try to use existing memory or create new one
            memory_name = "customerSupportMemory"
            
            try:
                memories_response = self.memory_client.list_memories()
                memories_list = memories_response.get('memories', []) if isinstance(memories_response, dict) else memories_response
                
                # Look for existing memory
                existing_memory = next(
                    (m for m in memories_list if memory_name in m.get('id', '')), 
                    None
                )
                
                if existing_memory:
                    self.memory_id = existing_memory['id']
                    logger.info(f"Using existing memory: {self.memory_id}")
                else:
                    # Create new memory
                    memory = self.memory_client.create_memory_and_wait(
                        name=memory_name,
                        description="Customer Support Agent Memory",
                        strategies=[],
                        event_expiry_days=90
                    )
                    self.memory_id = memory['id']
                    logger.info(f"Created new memory: {self.memory_id}")
                
                self.initialized = True
                
            except Exception as e:
                logger.error(f"Failed to initialize memory: {str(e)}")
                self.initialized = False
                
        except ImportError:
            logger.warning("bedrock_agentcore not available, memory disabled")
            self.initialized = False
        except Exception as e:
            logger.error(f"Memory initialization failed: {str(e)}")
            self.initialized = False
    
    def _ensure_session_table_exists(self):
        """Create DynamoDB table for session metadata if it doesn't exist"""
        try:
            self.session_table = self.dynamodb.Table(self.session_table_name)
            self.session_table.load()
            logger.info(f"Using existing DynamoDB table: {self.session_table_name}")
        except Exception as e:
            if "ResourceNotFoundException" in str(e):
                logger.info(f"Creating DynamoDB table: {self.session_table_name}")
                self._create_session_table()
            else:
                logger.error(f"Error accessing session table: {e}")
    
    def _create_session_table(self):
        """Create the DynamoDB session table"""
        try:
            self.session_table = self.dynamodb.create_table(
                TableName=self.session_table_name,
                KeySchema=[
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'session_id', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'session_id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            self.session_table.wait_until_exists()
            logger.info(f"DynamoDB table created: {self.session_table_name}")
        except Exception as e:
            logger.error(f"Failed to create session table: {e}")
    
    def _sanitize_actor_id(self, user_id: str) -> str:
        """Sanitize user ID to meet AgentCore actor ID requirements"""
        import re
        # Replace @ and . with underscores, keep only alphanumeric, hyphens, underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
        # Ensure it starts with alphanumeric
        sanitized = re.sub(r'^[^a-zA-Z0-9]+', '', sanitized)
        # Ensure it ends with alphanumeric, underscore, or hyphen
        sanitized = re.sub(r'[^a-zA-Z0-9_-]+$', '', sanitized)
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        return sanitized or 'user'
    
    def store_message(self, user_id: str, session_id: str, message: str, response: str):
        """Store user message and assistant response in AgentCore memory"""
        if not self.initialized:
            return
        
        try:
            # Sanitize actor ID for AgentCore
            actor_id = self._sanitize_actor_id(user_id)
            base_timestamp = datetime.now()
            
            # Store user message
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(message, "USER")],
                event_timestamp=base_timestamp
            )
            
            # Store assistant response with slight delay to maintain order
            import time
            time.sleep(0.1)
            response_timestamp = datetime.now()
            
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(response, "ASSISTANT")],
                event_timestamp=response_timestamp
            )
            
            # Update session metadata in DynamoDB
            self._update_session_metadata(user_id, session_id, message, response)
            
            logger.info(f"Stored messages for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error storing messages: {str(e)}")
    
    def get_session_messages(self, user_id: str, session_id: str) -> List[Dict]:
        """Get all messages for a specific session from AgentCore memory"""
        if not self.initialized:
            return []
        
        try:
            # Sanitize actor ID for AgentCore
            actor_id = self._sanitize_actor_id(user_id)
            
            events = self.memory_client.list_events(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                max_results=100
            )
            
            messages = []
            # events is a list directly
            for event in events:
                # Parse AgentCore event format
                if 'payload' in event and event['payload']:
                    payload = event['payload'][0]
                    if 'conversational' in payload:
                        conv = payload['conversational']
                        role_str = conv.get('role', 'USER')
                        content = conv.get('content', {}).get('text', '')
                        
                        if content:
                            role = 'user' if role_str == 'USER' else 'assistant'
                            messages.append({
                                'role': role,
                                'content': content,
                                'timestamp': event.get('eventTimestamp', '')
                            })
            
            # Sort by timestamp to maintain order
            messages = sorted(messages, key=lambda x: x.get('timestamp', ''))
            logger.info(f"Retrieved {len(messages)} messages for session {session_id}")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting session messages: {str(e)}")
            return []
    
    def get_conversation_context(self, user_id: str, session_id: str, query: str, max_messages: int = 10) -> str:
        """Get recent conversation context for enhanced responses"""
        messages = self.get_session_messages(user_id, session_id)
        recent_messages = messages[-max_messages:] if messages else []
        
        context_parts = []
        for msg in recent_messages:
            role = "Human" if msg['role'] == 'user' else "Assistant"
            content = msg['content'][:200]  # Truncate for context
            context_parts.append(f"{role}: {content}")
        
        return "\n".join(context_parts)
    
    def get_user_preferences(self, user_id: str) -> Dict:
        """Extract user preferences from conversation history"""
        # Get recent sessions for the user
        sessions = self.get_user_sessions(user_id, limit=5)
        
        preferences = {
            'communication_style': 'professional',
            'preferred_topics': [],
            'common_issues': [],
            'response_length': 'medium'
        }
        
        # Analyze conversation patterns
        all_messages = []
        for session in sessions:
            session_messages = self.get_session_messages(user_id, session['session_id'])
            all_messages.extend(session_messages)
        
        # Extract patterns from user messages
        user_messages = [msg for msg in all_messages if msg['role'] == 'user']
        for msg in user_messages[-20:]:  # Last 20 user messages
            content = msg['content'].lower()
            
            if 'warranty' in content:
                preferences['common_issues'].append('warranty')
            elif 'profile' in content or 'account' in content:
                preferences['common_issues'].append('account')
            elif 'mars' in content or 'weather' in content:
                preferences['preferred_topics'].append('space_data')
        
        # Remove duplicates
        preferences['common_issues'] = list(set(preferences['common_issues']))
        preferences['preferred_topics'] = list(set(preferences['preferred_topics']))
        
        return preferences
    
    def generate_follow_up_questions(self, user_id: str, current_query: str) -> List[str]:
        """Generate contextual follow-up questions based on user history"""
        preferences = self.get_user_preferences(user_id)
        
        follow_ups = []
        
        # Based on common issues
        if 'warranty' in preferences.get('common_issues', []):
            follow_ups.append("Would you like me to check the warranty status of any other products?")
        
        if 'account' in preferences.get('common_issues', []):
            follow_ups.append("Do you need help updating your account information?")
        
        # Based on current query context
        current_lower = current_query.lower()
        if 'warranty' in current_lower:
            follow_ups.extend([
                "Would you like me to explain the warranty coverage details?",
                "Do you need help with a warranty claim process?"
            ])
        elif 'profile' in current_lower or 'customer' in current_lower:
            follow_ups.extend([
                "Would you like to update any of your profile information?",
                "Do you need help with your communication preferences?"
            ])
        elif 'mars' in current_lower:
            follow_ups.extend([
                "Would you like to know about Mars atmospheric conditions?",
                "Are you interested in historical Mars weather data?"
            ])
        
        return follow_ups[:3]  # Return top 3 follow-ups
    
    def _update_session_metadata(self, user_id: str, session_id: str, last_message: str, response: str):
        """Update session metadata in DynamoDB"""
        if not self.session_table:
            logger.warning("Session table not available for metadata update")
            return
        
        try:
            timestamp = datetime.now().isoformat()
            
            # Get existing item to increment message count
            try:
                existing = self.session_table.get_item(
                    Key={'user_id': user_id, 'session_id': session_id}
                )
                message_count = existing.get('Item', {}).get('message_count', 0) + 1
            except:
                message_count = 1
            
            # Create or update session metadata
            self.session_table.put_item(
                Item={
                    'user_id': user_id,
                    'session_id': session_id,
                    'last_message': last_message[:100],  # Truncate for storage
                    'last_response': response[:100],
                    'last_updated': timestamp,
                    'message_count': message_count
                }
            )
            
            logger.info(f"Updated session metadata for {session_id}")
            
        except Exception as e:
            logger.error(f"Error updating session metadata: {e}")
    
    def get_user_sessions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get recent sessions for a user from DynamoDB"""
        if not self.session_table:
            logger.warning("Session table not available")
            return []
        
        try:
            # First check if table exists and is accessible
            self.session_table.load()
            
            response = self.session_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
                ScanIndexForward=False,
                Limit=limit
            )
            
            sessions = response.get('Items', [])
            logger.info(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            # Return empty list but don't fail completely
            return []
    
    def create_session(self, user_id: str) -> str:
        """Create a new session ID and store metadata"""
        session_id = f"session-{uuid.uuid4()}"
        
        # Store initial session metadata
        if self.session_table:
            try:
                timestamp = datetime.now().isoformat()
                self.session_table.put_item(
                    Item={
                        'user_id': user_id,
                        'session_id': session_id,
                        'last_message': 'New session started',
                        'last_response': '',
                        'last_updated': timestamp,
                        'message_count': 0
                    }
                )
                logger.info(f"Created session metadata for {session_id}")
            except Exception as e:
                logger.error(f"Error creating session metadata: {e}")
        else:
            logger.warning("Session table not available, session metadata not stored")
        
        return session_id
    
    def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete a session from both AgentCore memory and DynamoDB"""
        try:
            # Sanitize actor ID for AgentCore
            actor_id = self._sanitize_actor_id(user_id)
            
            # Get all events for this session
            events = self.memory_client.list_events(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                max_results=100
            )
            
            # Delete each event
            deleted_count = 0
            for event in events:
                try:
                    self.memory_client.delete_event(
                        memoryId=self.memory_id,
                        sessionId=session_id,
                        eventId=event['eventId'],
                        actorId=actor_id
                    )
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete event {event.get('eventId', 'unknown')}: {e}")
            
            # Delete session metadata from DynamoDB
            if self.session_table:
                try:
                    self.session_table.delete_item(
                        Key={'user_id': user_id, 'session_id': session_id}
                    )
                    logger.info(f"Deleted session metadata for {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete session metadata: {e}")
            
            logger.info(f"Deleted session {session_id}: {deleted_count} events removed")
            return deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {str(e)}")
            return False
    
    def is_available(self) -> bool:
        """Check if AgentCore memory is available"""
        return self.initialized and self.memory_client is not None


def create_agentcore_memory_manager(region: str = "us-east-1") -> AgentCoreMemoryManager:
    """Create and initialize AgentCore memory manager"""
    return AgentCoreMemoryManager(region=region)