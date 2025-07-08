from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from llama_cpp import Llama
import os
import sys
from colorama import Fore, Style, init
import warnings
import logging
logging.getLogger("llama_cpp").setLevel(logging.CRITICAL)

warnings.filterwarnings("ignore", category=DeprecationWarning)
init(autoreset=True)

# Load vector DB
print(Fore.YELLOW + "Loading vector database...")
embedding = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
db = Chroma(persist_directory="chatbot/embeddings", embedding_function=embedding)
retriever = db.as_retriever(search_kwargs={"k": 3})
print(Fore.GREEN + "Vector DB loaded.")

# Load LLM
print(Fore.YELLOW + "Loading Mistral 7B model...")
model_path = os.path.join("chatbot/models", "mistral-7b-instruct-v0.1.Q4_K_M.gguf")
llm = Llama(
    model_path=model_path,
    n_ctx=2048,
    n_threads=6,
    use_mlock=True,
    verbose=False
)
print(Fore.GREEN + "Model loaded. You can now chat with your documents.")

# Chat loop
try:
    while True:
        query = input(Fore.CYAN + "\nYou: ")
        if query.strip().lower() in ['exit', 'quit']:
            print(Fore.YELLOW + "Exiting... Goodbye!")
            break

        docs = retriever.get_relevant_documents(query)
        if not docs or all(not doc.page_content.strip() for doc in docs):
            prompt = f"""
You are a friendly assistant. The user asked something casual or not covered by the documents.
Please respond kindly and helpfully, even without context.

[Question]
{query}

Answer:"""
        else:
            # Normal doc-based prompt
            context = "\n".join([doc.page_content for doc in docs])
            prompt = f"""
You are a helpful assistant. Use the provided context to answer the user's question.

[Context]
{context}

[Question]
{query}

Answer:"""

        # Get LLM response
        response = llm(prompt, max_tokens=512, stop=["</s>"])
        answer = response["choices"][0]["text"].strip()

        print(Fore.GREEN + "\nBot: " + Style.RESET_ALL + answer)

except KeyboardInterrupt:
    print(Fore.YELLOW + "\n\nExited via keyboard. Bye!")
    sys.exit(0)

