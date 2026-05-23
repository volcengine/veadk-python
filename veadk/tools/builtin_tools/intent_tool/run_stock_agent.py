'''
Author: haoxingjun
Date: 2026-01-27 13:06:07
Email: haoxingjun@bytedance.com
LastEditors: haoxingjun
LastEditTime: 2026-01-27 13:12:59
Description: file information
Company: ByteDance
'''
import os
import sys

# Ensure veadk is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from veadk.tools.builtin_tools.intent_tool.governance import IntentGovernor
from veadk.tools.builtin_tools.intent_tool.retriever import StockRetriever

def main():
    # 0. Setup
    print("Initializing components...")
    
    # Ensure API keys are set (mock check or rely on env)
    if not os.environ.get("ARK_API_KEY") and not os.environ.get("MODEL_AGENT_API_KEY"):
        print("Warning: ARK_API_KEY or MODEL_AGENT_API_KEY not found in environment.")
        # return # Proceeding might fail, but let's let it fail naturally or user sets it.

    governor = IntentGovernor() # Defaults to using the prompt in veadk/tools/builtin_tools/intent_tool/prompts
    
    # collection_name = "test_factor_haoxingjun" # Default from original script
    retriever = StockRetriever(collection_name="stock_factors_kb")
    
    # Simulation Loop
    query = "前2月销额累计值同比稳增的半导体股"
    print(f"\nUser Query: {query}")
    print("-" * 50)
    
    # Step 1: Governance
    print("[Step 1] Governance: Analyzing Intent...")
    intent_result = governor.process(query)
    print(f"Governance Result: {intent_result}")
    
    if intent_result.get("status") != "PROCEED":
        print(f"需澄清: {intent_result.get('message')}")
        return

    # Step 2: Retrieval
    print("\n[Step 2] Retrieval: Fetching Context...")
    # governor returns payload in "payload" key
    payload = intent_result.get("payload")
    context_data = retriever.retrieve(payload)
    
    print("检索到的上下文:")
    print(context_data["context_str"])
    
    # Step 3: Response (Mock)
    print("\n[Step 3] Response: Generating Answer...")
    # llm.chat(query, context=context_data["context_str"]) 
    print("-" * 50)
    print("AI: (Mock Response) 基于检索结果，前2月半导体行业销额累计值同比稳增的股票包括...")

if __name__ == "__main__":
    main()
