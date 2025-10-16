# services/vectorstore_singleton.py
import os 
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from utils.constants import VECTOR_DIR, EMBEDDING_MODEL,VECTORSTORE_BASE
from dotenv import load_dotenv
from services import file_service
from services.vectorstore_loader import get_openai_api_key
load_dotenv()
EMBEDDING = os.getenv("EMBEDDING")
vectorstore = None
retriever = None

def get_embedding_model():
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=get_openai_api_key())

def get_vectorstore_for_org(org_id):
    vectorstore_dir = os.path.join(VECTORSTORE_BASE, f"org_{org_id}")
    embeddings = get_embedding_model()
    return FAISS.load_local(vectorstore_dir, embeddings)

def load_faiss_vectorstore(org_id: str):
    vectorstore_dir = file_service.get_org_vectorstore_dir(org_id)
    embedding_model = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=get_openai_api_key()
    )
    return FAISS.load_local(vectorstore_dir, embedding_model, allow_dangerous_deserialization=True)


# Helper to get retriever for an org
def get_retriever(org_id: str):
    vectorstore = load_faiss_vectorstore(org_id)
    return vectorstore.as_retriever(search_kwargs={"k": 3})

# If you want reload functionality:
def reload_vectorstore(org_id: str):
    # Optionally, just reload the vectorstore for the org
    return load_faiss_vectorstore(org_id)
