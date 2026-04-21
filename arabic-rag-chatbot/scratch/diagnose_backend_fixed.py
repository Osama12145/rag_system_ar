
import os
from dotenv import load_dotenv
import asyncio
from langchain_cohere import CohereEmbeddings
from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient

load_dotenv()

async def test_key():
    print("--- Testing API Keys ---")
    cohere_key = os.getenv("COHERE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if not cohere_key:
        print("[ERROR] COHERE_API_KEY is missing!")
    if not openrouter_key:
        print("[ERROR] OPENROUTER_API_KEY is missing!")

    print("\n--- Testing Cohere Embeddings ---")
    try:
        embeddings = CohereEmbeddings(
            cohere_api_key=cohere_key,
            model="embed-multilingual-v3.0"
        )
        test_vec = embeddings.embed_query("سلام")
        print(f"[SUCCESS] Cohere Success! Vector size: {len(test_vec)}")
    except Exception as e:
        print(f"[FAILED] Cohere Failed: {e}")

    print("\n--- Testing OpenRouter (ChatOpenAI) ---")
    try:
        llm = ChatOpenAI(
            model_name="cohere/command-r7b-12-2024",
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        response = llm.invoke("Hi")
        print(f"[SUCCESS] OpenRouter Success! Response: {response.content[:50]}...")
    except Exception as e:
        print(f"[FAILED] OpenRouter Failed: {e}")

    print("\n--- Testing Qdrant Local ---")
    try:
        client = QdrantClient(path="./qdrant_local_db")
        collections = client.get_collections()
        print(f"[SUCCESS] Qdrant Success! Collections: {[c.name for c in collections.collections]}")
    except Exception as e:
        print(f"[FAILED] Qdrant Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_key())
