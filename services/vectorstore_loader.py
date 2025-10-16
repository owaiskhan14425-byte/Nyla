import os
import shutil
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from utils.constants import VECTOR_DIR, EMBEDDING_MODEL
from dotenv import load_dotenv
from utils.logger import log_error
from services import file_service

load_dotenv()

def get_openai_api_key():
    key = os.getenv("EMBEDDING")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set in environment variables.")
    return key

UPLOAD_DIR = "pdf_files"
FAISS_INDEX_FACTORY = "HNSW32" 

def batch_retrain_all_orgs():
    pdf_base = "pdf_files"
    # Get all org folders in pdf_files (they start with "org_")
    org_dirs = [
        name for name in os.listdir(pdf_base)
        if os.path.isdir(os.path.join(pdf_base, name)) and name.startswith("org_")
    ]
    print(f"Found {len(org_dirs)} orgs: {org_dirs}")

    for org_folder in org_dirs:
        org_id = org_folder.replace("org_", "")
        print(f"Retraining vectorstore for org: {org_id}")
        try:
            retrain_and_replace_vectorstore(org_id)
        except Exception as e:
            print(f"❌ Error retraining org {org_id}: {e}")
    return 'trained'


def retrain_and_replace_vectorstore(org_id: str):
    upload_dir = os.path.join("pdf_files", f"org_{org_id}")
    vectorstore_dir = os.path.join("vectorstores", f"org_{org_id}")
    all_documents = []

    # NEW: if no upload dir, clear any existing index and stop
    if not os.path.isdir(upload_dir):
        shutil.rmtree(vectorstore_dir, ignore_errors=True)
        print(f"No upload dir for org: {org_id}; cleared index.")
        return False  # <-- return a boolean

    for filename in os.listdir(upload_dir):
        # NEW: skip hidden files and folders
        if filename.startswith("."):
            continue
        file_path = os.path.join(upload_dir, filename)
        if os.path.isdir(file_path):
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            loader = PyMuPDFLoader(file_path)
        elif ext == ".txt":
            loader = TextLoader(file_path)
        elif ext == ".docx":
            loader = Docx2txtLoader(file_path)
        else:
            continue

        try:
            docs = loader.load()
            lower_docs = [
                Document(page_content=doc.page_content.lower(), metadata=doc.metadata)
                for doc in docs
            ]
            all_documents.extend(lower_docs)
        except Exception as e:
            print(f"❌ Error loading {filename}: {e}")
            log_error(f"❌ Error loading {filename}: {e}")

    # NEW: if no docs, remove any existing index dir and stop
    if not all_documents:
        shutil.rmtree(vectorstore_dir, ignore_errors=True)
        print(f"No valid documents found to index for org: {org_id}; cleared index.")
        return False

    # Recreate index dir only when we actually have docs
    if os.path.exists(vectorstore_dir):
        shutil.rmtree(vectorstore_dir, ignore_errors=True)
    os.makedirs(vectorstore_dir, exist_ok=True)

    splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
    docs = splitter.split_documents(all_documents)

    embedding_model = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=get_openai_api_key()
    )
    vectorstore = FAISS.from_documents(docs, embedding_model)
    vectorstore.save_local(vectorstore_dir)
    print(f"Vectorstore saved for org: {org_id}")
    return True  # <-- indicate success


