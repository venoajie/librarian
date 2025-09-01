
(.venv-ai-tools) [opc@instance-20250707-0704 app]$ cat main.py
#  app\main.py

import uvloop
uvloop.install()

import logging
import redis.asyncio as redis
import chromadb
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter
from app.core.config import settings
from app.api.v1.router import api_router
from app.models.schemas import IndexStatus
from app.core import index_manager

# --- Setup Logging ---
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info(f"Starting Librarian Service v{settings.SERVICE_VERSION}")

    # --- Initialize State ---
    app.state.index_status = IndexStatus.LOADING
    app.state.index_last_modified = None

    # --- Initialize Redis Client ---
    try:
        app.state.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await app.state.redis_client.ping()
        logger.info("Successfully connected to Redis.")
    except Exception as e:
        app.state.redis_client = None
        logger.error(f"Could not connect to Redis: {e}", exc_info=True)

    # --- Load Sentence Transformer Model ---
    try:
        logger.info("Loading sentence-transformer model into memory...")
        model_name = "all-MiniLM-L6-v2"
        app.state.embedding_model = SentenceTransformer(model_name)
        logger.info(f"Model '{model_name}' loaded successfully.")
    except Exception as e:
        app.state.embedding_model = None
        logger.critical(f"CRITICAL: Failed to load sentence-transformer model: {e}", exc_info=True)

    # --- Load ChromaDB Index ---
    archive_path = Path("/tmp/index.tar.gz")
    index_path = Path(settings.CHROMA_DB_PATH)

    #index_manager._mock_oci_download(archive_path)
    downloaded =  index_manager.download_index_from_oci(archive_path)

    if downloaded and index_manager.unpack_index(archive_path, index_path):
        try:
            chroma_client = chromadb.PersistentClient(path=str(index_path))
            app.state.chroma_collection = chroma_client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}  # This ensures consistency
            )
            app.state.index_status = IndexStatus.LOADED
            app.state.index_last_modified = datetime.utcnow()
            logger.info(f"ChromaDB index '{settings.CHROMA_COLLECTION_NAME}' loaded successfully.")
        except Exception as e:
            app.state.chroma_collection = None
            app.state.index_status = IndexStatus.NOT_FOUND
            logger.error(f"Failed to load ChromaDB collection: {e}", exc_info=True)
    else:
        app.state.chroma_collection = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.error("Index setup failed due to download or unpacking error.")

    yield

    # --- Shutdown ---
    logger.info("Shutting down Librarian Service.")
    if app.state.redis_client:
        await app.state.redis_client.close()
        logger.info("Redis connection closed.")

app = FastAPI(
    title="Librarian RAG Service",
    description="A centralized service for retrieving codebase context.",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    default_response_class=ORJSONResponse,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_router, prefix="/api/v1")

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Welcome to the Librarian RAG Service. See /api/docs for details."}
(.venv-ai-tools) [opc@instance-20250707-0704 app]$ cd librarian
-bash: cd: librarian: No such file or directory
(.venv-ai-tools) [opc@instance-20250707-0704 app]$ ls
api  core  __init__.py  main.py  models
(.venv-ai-tools) [opc@instance-20250707-0704 app]$ cd ..
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ docker compose down -v
[+] Running 5/5
 ✔ Container librarian-service-1           Removed                                                                                                                     2.0s
 ✔ Container librarian-redis-1             Removed                                                                                                                     0.3s
 ✔ Volume librarian_librarian_redis_data   Removed                                                                                                                     0.0s
 ✔ Volume librarian_librarian_chroma_data  Removed                                                                                                                     0.0s
 ✔ Network librarian_librarian-net         Removed                                                                                                                     0.4s
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ sudo rm -rf /data/librarian/chroma
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ mkdir -p /data/librarian/chroma
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ sudo chown opc:opc /data/librarian/chroma
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ docker compose build --no-cache
#1 [internal] load local bake definitions
#1 reading from stdin 533B done
#1 DONE 0.0s

#2 [internal] load build definition from Dockerfile
#2 transferring dockerfile: 1.93kB done
#2 DONE 0.0s

#3 [internal] load metadata for docker.io/library/python:3.12-slim
#3 DONE 0.7s

#4 [internal] load .dockerignore
#4 transferring context: 2B done
#4 DONE 0.0s

#5 [base 1/2] FROM docker.io/library/python:3.12-slim@sha256:d67a7b66b989ad6b6d6b10d428dcc5e0bfc3e5f88906e67d490c4d3daac57047
#5 CACHED

#6 [internal] load build context
#6 transferring context: 2.12kB done
#6 DONE 0.0s

#7 [base 2/2] RUN python -m pip install --no-cache-dir uv     && python -m uv venv /opt/venv
#7 1.997 Collecting uv
#7 2.032   Downloading uv-0.8.14-py3-none-manylinux_2_28_aarch64.whl.metadata (11 kB)
#7 2.039 Downloading uv-0.8.14-py3-none-manylinux_2_28_aarch64.whl (18.4 MB)
#7 2.123    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 18.4/18.4 MB 262.3 MB/s eta 0:00:00
#7 2.146 Installing collected packages: uv
#7 2.360 Successfully installed uv-0.8.14
#7 2.361 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#7 2.417
...
#9 DONE 13.7s

#10 [builder 2/4] WORKDIR /build
#10 DONE 0.0s

#11 [builder 3/4] COPY pyproject.toml .
#11 DONE 0.0s

#12 [builder 4/4] RUN uv pip install --no-cache --strict .
#12 0.245 Using Python 3.12.11 environment at: /opt/venv
#12 1.556 Resolved 114 packages in 1.30s
#12 1.563    Building librarian @ file:///build
#12 1.572 Downloading pygments (1.2MiB)
#12 1.576 Downloading transformers (11.1MiB)
#12 1.577 Downloading sympy (6.0MiB)
#12 1.578 Downloading kubernetes (1.9MiB)
#12 1.578 Downloading networkx (1.9MiB)
#12 1.579 Downloading onnxruntime (5.7MiB)
#12 1.579 Downloading numpy (13.6MiB)
#12 1.592 Downloading uvloop (4.4MiB)
#12 1.592 Downloading pydantic-core (1.7MiB)
#12 1.592 Downloading scipy (31.8MiB)
#12 1.592 Downloading oci (24.5MiB)
#12 1.593 Downloading torch (84.3MiB)
#12 1.593 Downloading tokenizers (3.1MiB)
#12 1.594 Downloading cryptography (3.5MiB)
#12 1.596 Downloading grpcio (5.7MiB)
#12 1.596 Downloading hf-xet (2.9MiB)
#12 1.604 Downloading pillow (5.7MiB)
#12 1.604 Downloading scikit-learn (8.9MiB)
#12 1.605 Downloading chromadb (18.0MiB)
#12 2.257    Building pypika==0.48.9
#12 2.271    Building circuitbreaker==1.4.0
#12 2.468       Built librarian @ file:///build
#12 2.622       Built circuitbreaker==1.4.0
#12 2.633  Downloading pydantic-core
#12 2.650       Built pypika==0.48.9
#12 2.749  Downloading py
...
#12 DONE 11.7s

#13 [runtime 2/6] COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
#13 DONE 9.3s

#14 [runtime 3/6] WORKDIR /app
#14 DONE 0.0s

#15 [runtime 4/6] RUN mkdir -p /data/chroma
#15 DONE 0.2s

#16 [runtime 5/6] COPY --chown=appuser:appuser ./app ./app
#16 DONE 0.0s

#17 [runtime 6/6] RUN chown -R appuser:appuser /app /data
#17 DONE 0.2s

#18 exporting to image
#18 exporting layers
#18 exporting layers 8.1s done
#18 writing image sha256:1a88b350c03793adeff187aee16fbdf2c4fa418ece02e189d1d6921e93c46113 done
#18 naming to docker.io/library/librarian-librarian done
#18 DONE 8.1s

#19 resolving provenance for metadata file
#19 DONE 0.0s
[+] Building 1/1
 ✔ librarian-librarian  Built                                                                                                                                          0.0s
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ docker compose up -d
[+] Running 5/5
 ✔ Network librarian_librarian-net           Created                                                                                                                   0.2s
 ✔ Volume "librarian_librarian_redis_data"   Created                                                                                                                   0.0s
 ✔ Volume "librarian_librarian_chroma_data"  Created                                                                                                                   0.0s
 ✔ Container librarian-redis-1               Healthy                                                                                                                   5.8s
 ✔ Container librarian-service-1             Started                                                                                                                   6.0s
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ API_KEY=$(cat ./secrets/librarian_api_key.txt)
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ curl -X POST "http://localhost:8000/api/v1/context" \
> -H "Content-Type: application/json" \
> -H "X-API-KEY: $API_KEY" \
> -d '{
>   "query": "How is the rate limiter configured?",
>   "max_results": 2
> }' | python -m json.tool
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   160  100    88  100    72   1313   1074 --:--:-- --:--:-- --:--:--  2388
{
    "query_id": "b40dccc5-cf55-4f20-ae4b-253700c495fa",
    "context": [],
    "processing_time_ms": 60
}
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ cd ..
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ cat main.py
cat: main.py: No such file or directory
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ ls
create_index.py  index_build  index.tar.gz  librarian  trading-app
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ cat create_index.py
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

    # --- CRITICAL FIX: Manually create embeddings before adding to ChromaDB ---
    print("5. Generating embeddings for all text chunks...")
    embeddings = model.encode(all_chunks, show_progress_bar=True)
    # --- END FIX ---

    batch_size = 100
    print(f"6. Adding documents to ChromaDB in batches of {batch_size}...")
    for i in tqdm(range(0, len(all_chunks), batch_size), desc="Storing in ChromaDB"):
        batch_docs = all_chunks[i:i+batch_size]
        batch_metadatas = all_metadatas[i:i+batch_size]
        batch_embeddings = embeddings[i:i+batch_size]
        batch_ids = [f"{meta['source']}_{meta['chunk_id']}" for meta in batch_metadatas]

        # --- CRITICAL FIX: Add the pre-computed embeddings ---
        collection.add(
            embeddings=batch_embeddings.tolist(), # Pass the embeddings
            documents=batch_docs,                # Still pass documents for storage
            metadatas=batch_metadatas,
            ids=batch_ids
        )
        # --- END FIX ---

    print(f"✅ ChromaDB index created with {collection.count()} entries.")

def package_index(output_file: str = "index.tar.gz"):
    print(f"7. Packaging index into '{output_file}'...")
    build_dir = Path(CHROMA_DB_PATH).parent
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(build_dir, arcname=build_dir.name)
    print(f"✅ Index packaged successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create and package a ChromaDB index from a source code directory.")
    parser.add_argument("source_directory", type=str, help="The path to the source code directory to index.")
    args = parser.parse_args()

    create_index_from_directory(args.source_directory)
    package_index()
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ API_KEY=$(cat ./secrets/librarian_api_key.txt)
cat: ./secrets/librarian_api_key.txt: No such file or directory
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ ls -lh
total 164K
-rw-r--r--.  1 opc opc 3.9K Sep  1 02:33 create_index.py
drwxr-xr-x.  3 opc opc 4.0K Sep  1 02:37 index_build
-rw-r--r--.  1 opc opc 148K Sep  1 02:37 index.tar.gz
drwxr-xr-x.  5 opc opc 4.0K Sep  1 01:21 librarian
drwxr-xr-x. 17 opc opc 4.0K Aug 30 09:16 trading-app
(.venv-ai-tools) [opc@instance-20250707-0704 apps]$ cd librarian
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ ls -lh
total 32K
drwxr-xr-x. 5 opc opc 4.0K Sep  1 02:37 app
-rw-r--r--. 1 opc opc 1.4K Sep  1 00:16 docker-compose.yml
-rw-r--r--. 1 opc opc 1.8K Sep  1 00:57 Dockerfile
-rw-r--r--. 1 opc opc  572 Sep  1 01:21 pyproject.toml
-rw-r--r--. 1 opc opc 7.5K Aug 31 10:15 README.md
-rw-r--r--. 1 opc opc  956 Aug 31 10:15 requirements.txt
drwxr-xr-x. 2 opc opc 4.0K Aug 31 11:49 secrets
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ API_KEY=$(cat ./secrets/librarian_api_key.txt)
(.venv-ai-tools) [opc@instance-20250707-0704 librarian]$ curl -X POST "http://localhost:8000/api/v1/context" -H "Content-Type: application/json" -H "X-API-KEY: $API_KEY" -d '{
  "query": "How is the rate limiter configured?",
  "max_results": 2
}' | python -m json.tool
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   160  100    88  100    72   2095   1714 --:--:-- --:--:-- --:--:--  3809
{
    "query_id": "b2c8da83-536c-4da1-8c3a-7ca5ff95cf2f",
    "context": [],
    "processing_time_ms": 38
}