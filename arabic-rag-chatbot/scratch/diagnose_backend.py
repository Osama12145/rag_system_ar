
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
    
    print(f"Cohere Key (masked): {cohere_key[:5]}...{cohere_key[-5:] if cohere_key else 'None'}")
    print(f"OpenRouter Key (masked): {openrouter_key[:5]}...{openrouter_key[-5:] if openrouter_key else 'None'}")

    print("\n--- Testing Cohere Embeddings ---")
    try:
        embeddings = CohereEmbeddings(
            cohere_api_key=cohere_key,
            model="embed-multilingual-v3.0"
        )
        test_vec = embeddings.embed_query("سلام")
        print(f"✅ Cohere Success! Vector size: {len(test_vec)}")
    except Exception as e:
        print(f"❌ Cohere Failed: {e}")

    print("\n--- Testing OpenRouter (ChatOpenAI) ---")
    try:
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        response = llm.invoke("Hi")
        print(f"✅ OpenRouter Success! Response: {response.content[:50]}...")
    except Exception as e:
        print(f"❌ OpenRouter Failed: {e}")

    print("\n--- Testing Qdrant Local ---")
    try:
        client = QdrantClient(path="./qdrant_local_db")
        collections = client.get_collections()
        print(f"✅ Qdrant Success! Collections: {[c.name for c in collections.collections]}")
    except Exception as e:
        print(f"❌ Qdrant Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_key())
