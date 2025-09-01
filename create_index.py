import os
import tarfile
import chromadb
import argparse
from pathlib import Path
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

# --- CONFIGURATION ---
CHROMA_DB_PATH = "./index_build/chroma"
CHROMA_COLLECTION_NAME = "codebase_collection"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
# --- END CONFIGURATION ---

def create_index_from_directory(source_dir: str):
    source_path = Path(source_dir)
    if not source_path.is_dir():
        print(f"Error: Source directory '{source_dir}' not found.")
        return

    print(f"1. Loading embedding model '{EMBEDDING_MODEL_NAME}'...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    print(f"2. Initializing ChromaDB at '{CHROMA_DB_PATH}'...")
    if Path(CHROMA_DB_PATH).exists():
        import shutil
        shutil.rmtree(CHROMA_DB_PATH)

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection =  client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # This is the critical change
    )

    print(f"3. Scanning and processing files in '{source_dir}'...")
    extensions = ['.py', '.md', '.txt', '.json', '.yml', '.yaml', '.sh']
    files_to_process = [p for p in source_path.rglob('*') if p.suffix in extensions]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_chunks, all_metadatas = [], []

    for file_path in tqdm(files_to_process, desc="Reading files"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            chunks = text_splitter.split_text(content)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({"source": str(file_path.relative_to(source_path)), "chunk_id": i})
        except Exception as e:
            print(f"\nWarning: Could not process {file_path}: {e}")

    print(f"4. Found {len(all_chunks)} text chunks to embed.")
    if not all_chunks:
        print("No text chunks found. Exiting.")
        return

    print("5. Generating embeddings for all text chunks...")
    embeddings = model.encode(all_chunks, show_progress_bar=True)

    batch_size = 100
    print(f"6. Adding documents to ChromaDB in batches of {batch_size}...")
    for i in tqdm(range(0, len(all_chunks), batch_size), desc="Storing in ChromaDB"):
        batch_docs = all_chunks[i:i+batch_size]
        batch_metadatas = all_metadatas[i:i+batch_size]
        batch_embeddings = embeddings[i:i+batch_size]
        batch_ids = [f"{meta['source']}_{meta['chunk_id']}" for meta in batch_metadatas]

        collection.add(
            embeddings=batch_embeddings.tolist(), # Pass the embeddings
            documents=batch_docs,                # Still pass documents for storage
            metadatas=batch_metadatas,
            ids=batch_ids
        )

    print(f"✅ ChromaDB index created with {collection.count()} entries.")

def package_index(output_file: str = "index.tar.gz"):
    print(f"7. Packaging index into '{output_file}'...")
    # The path to the directory we want to archive the contents of.
    source_dir = CHROMA_DB_PATH
    with tarfile.open(output_file, "w:gz") as tar
        # Add the contents of the source_dir to the root of the archive.
        tar.add(source_dir, arcname=".")
    print(f"✅ Index packaged successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create and package a ChromaDB index from a source code directory.")
    parser.add_argument("source_directory", type=str, help="The path to the source code directory to index.")
    args = parser.parse_args()

    create_index_from_directory(args.source_directory)
    package_index()