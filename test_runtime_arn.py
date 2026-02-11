import os
import logging
import streamlit as st
# from langgraph_main import initialize_database, process_enhanced_query

import json
import boto3

# from test_langgraph_agentcore import get_agent_core_result

@st.cache_resource
def get_agent_clients():
    """Initialize agent clients once and cache them"""
    agent_core_client = boto3.client('bedrock-agentcore', region_name="us-east-1",
                                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    
    control_client = boto3.client('bedrock-agentcore-control', region_name="us-east-1",
                                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    return agent_core_client, control_client

with open('deployment_info.json', 'r') as f:
    deployment_info = json.load(f)

runtime_execution_role_arn = deployment_info['runtime_execution_role_arn']
agentcore_runtime_arn = deployment_info['agentcore_runtime_arn']

def agentcore_runtime_invokation(query):
    runtime_arn = agentcore_runtime_arn
    
    # Get cached clients
    agent_core_client, control_client = get_agent_clients()
    
    # Generate unique session ID for each user session
    if 'session_id' not in st.session_state:
        import uuid
        st.session_state.session_id = f"session-{uuid.uuid4()}"
    
    payload = json.dumps({"prompt": query}).encode('utf-8')

    try:
        response = agent_core_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=st.session_state.session_id,
            payload=payload,
            qualifier="DEFAULT"
        )
        
        response_body = response['response'].read()
        response_data = json.loads(response_body)
        
        # Clean and format the response
        if isinstance(response_data, str):
            # Remove excessive whitespace and fix table formatting
            cleaned_response = response_data.replace('\n\n\n', '\n\n')
            cleaned_response = cleaned_response.replace('                    ', '')
            return cleaned_response
        
        return str(response_data)
        
    except Exception as e:
        error_msg = f"Error invoking agent runtime: {str(e)}"
        st.error(error_msg)
        return "I apologize, but I'm experiencing technical difficulties. Please try again in a moment."

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
query1 = "What is the weather in northern part of the mars?"

logger.info("Executing Query 1")
result = agentcore_runtime_invokation(query1)
logger.info(f"the result of query {query1} : {result}")

# Example 2: Check product warranty status
# The agent will use the Lambda function tool to query DynamoDB
logger.info("Executing Query 2")
query2 = "I have a Gaming Console Pro device , I want to check my warranty status, warranty serial number is MNO33333333."
result = agentcore_runtime_invokation(query2)
logger.info(f"the result of query {query2} : {result}")

