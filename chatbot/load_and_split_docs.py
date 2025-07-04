from langchain.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import os

def load_documents(doc_folder="chatbot/documents/"):
    all_docs = []
    for file in os.listdir(doc_folder):
        if file.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join(doc_folder, file))
        elif file.endswith(".docx"):
            loader = Docx2txtLoader(os.path.join(doc_folder, file))
        else:
            continue
        docs = loader.load()
        all_docs.extend(docs)
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    return splitter.split_documents(all_docs)
