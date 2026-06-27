import os
import re
import math
import hashlib
import json
import logging

log = logging.getLogger("vyom_rag")
logging.basicConfig(level=logging.INFO)

KB_DIR = r"c:\Users\ADMIN\Downloads\Classmind-main\knowledge_base"
CACHE_PATH = r"c:\Users\ADMIN\Downloads\Classmind-main\data\kb_embeddings.json"

SYNONYMS = {
    "struggling": ["at-risk", "weak", "failing", "poor", "risk"],
    "weak": ["struggling", "at-risk", "failing", "poor", "risk"],
    "at-risk": ["struggling", "weak", "failing", "poor", "risk"],
    "attendance": ["present", "absent", "roll", "joined", "timestamp", "leave", "sheet"],
    "chat": ["doubt", "message", "communication", "talk", "discuss", "conversation"],
    "doubt": ["question", "confused", "chat", "ask", "clarify", "resolved"],
    "analytics": ["chart", "graph", "metric", "statistics", "report", "data"],
    "report": ["excel", "pdf", "export", "download", "summary", "gradebook"],
    "test": ["exam", "cheat", "assessment", "quiz", "locked", "integrity"],
    "coding": ["program", "python", "javascript", "code", "compiler", "sandbox", "editor", "cases"],
    "session": ["class", "start", "end", "pause", "resume", "code"]
}

def tokenize(text):
    text = text.lower()
    text = re.sub(r'[^\w\s\-]', ' ', text)
    tokens = text.split()
    expanded = []
    for token in tokens:
        expanded.append(token)
        if token in SYNONYMS:
            expanded.extend(SYNONYMS[token])
    return expanded

class BM25Scorer:
    def __init__(self, chunks):
        """
        chunks: list of dict with 'id', 'text'
        """
        self.chunks = chunks
        self.doc_ids = [c['id'] for c in chunks]
        self.documents = {c['id']: tokenize(c['text']) for c in chunks}
        self.doc_len = {doc_id: len(words) for doc_id, words in self.documents.items()}
        self.avg_doc_len = sum(self.doc_len.values()) / len(self.doc_len) if self.doc_len else 1.0
        self.doc_count = len(self.documents)
        
        self.tf = {}
        for doc_id, words in self.documents.items():
            self.tf[doc_id] = {}
            for word in words:
                self.tf[doc_id][word] = self.tf[doc_id].get(word, 0) + 1
                
        self.df = {}
        for doc_id, words in self.documents.items():
            unique_words = set(words)
            for word in unique_words:
                self.df[word] = self.df.get(word, 0) + 1
                
        self.idf = {}
        for word, count in self.df.items():
            self.idf[word] = math.log((self.doc_count - count + 0.5) / (count + 0.5) + 1.0)
            
    def get_score(self, query_tokens, doc_id, k1=1.5, b=0.75):
        score = 0.0
        doc_words = self.documents[doc_id]
        doc_len = self.doc_len[doc_id]
        tf_dict = self.tf[doc_id]
        
        for token in query_tokens:
            if token not in tf_dict:
                continue
            tf_val = tf_dict[token]
            idf_val = self.idf.get(token, 0.0)
            numerator = tf_val * (k1 + 1)
            denominator = tf_val + k1 * (1 - b + b * (doc_len / self.avg_doc_len))
            score += idf_val * (numerator / denominator)
            
        return score

    def score_all(self, query):
        tokens = tokenize(query)
        scores = []
        for doc_id in self.doc_ids:
            score = self.get_score(tokens, doc_id)
            if score > 0:
                scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores


class RagEngine:
    def __init__(self):
        self.chunks = []
        self.bm25 = None
        self.load_documents()

    def load_documents(self):
        """Loads and chunks all markdown files from knowledge_base directory."""
        self.chunks = []
        if not os.path.exists(KB_DIR):
            log.warning("Knowledge base directory %s does not exist.", KB_DIR)
            return

        for filename in os.listdir(KB_DIR):
            if not filename.endswith(".md"):
                continue
            
            filepath = os.path.join(KB_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            source_name = filename[:-3].replace("_", " ").title()
            
            # Simple chunking by ## headings
            sections = re.split(r'\n(##\s+)', content)
            
            # First section (title + does)
            header_text = sections[0].strip()
            if header_text:
                self.chunks.append({
                    "id": f"{filename}:intro",
                    "file": filename,
                    "source": source_name,
                    "section": "Introduction",
                    "text": header_text
                })

            # Subsequent sections
            for i in range(1, len(sections), 2):
                header_prefix = sections[i]  # "## "
                sec_content = sections[i+1].strip() if i+1 < len(sections) else ""
                
                # Extract section title from the first line
                lines = sec_content.split("\n", 1)
                sec_title = lines[0].strip()
                sec_body = lines[1].strip() if len(lines) > 1 else ""
                
                self.chunks.append({
                    "id": f"{filename}:{sec_title.lower().replace(' ', '_')}",
                    "file": filename,
                    "source": source_name,
                    "section": sec_title,
                    "text": f"{header_prefix}{sec_title}\n\n{sec_body}".strip()
                })

        # Re-initialize BM25 index
        if self.chunks:
            self.bm25 = BM25Scorer(self.chunks)
            log.info("RAG Engine loaded %d chunks from %d files.", len(self.chunks), len(os.listdir(KB_DIR)))
        else:
            log.warning("No chunks found to initialize RAG Engine.")

    def get_chunk_by_id(self, chunk_id):
        for c in self.chunks:
            if c['id'] == chunk_id:
                return c
        return None

    async def get_embedding(self, text, api_key):
        """Fetches Gemini embedding for a given text."""
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "models/text-embedding-004",
                    "content": {"parts": [{"text": text}]}
                }
            )
            if resp.status_code == 200:
                return resp.json()["embedding"]["values"]
            else:
                log.warning("Gemini embedding API failed: %s", resp.text)
                return None

    def calculate_cosine_similarity(self, vec1, vec2):
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        return dot_product / (norm1 * norm2) if norm1 and norm2 else 0.0

    async def retrieve(self, query, top_n=4, api_key=None):
        """
        Retrieves top relevant chunks for a query.
        Uses Gemini embeddings if api_key is available, falling back to BM25.
        """
        # Reload documents dynamically to support incremental updates without server restart
        self.load_documents()

        if not self.chunks:
            return []

        # If api_key (Gemini) is available, try semantic vector search
        # Standard Gemini key starts with AIzaSy
        is_gemini_key = api_key and (api_key.startswith("AIzaSy") or "generativelanguage" in api_key)
        
        if is_gemini_key:
            try:
                # Load or initialize embedding cache
                cache = {}
                if os.path.exists(CACHE_PATH):
                    try:
                        with open(CACHE_PATH, "r", encoding="utf-8") as f:
                            cache = json.load(f)
                    except Exception as e:
                        log.warning("Failed to load embeddings cache: %s", e)

                cache_updated = False
                chunk_embeddings = {}

                # Calculate text hashes and load embeddings
                for chunk in self.chunks:
                    chunk_text = chunk["text"]
                    text_hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
                    
                    # Check cache hit
                    cached_data = cache.get(chunk["id"])
                    if cached_data and cached_data.get("hash") == text_hash:
                        chunk_embeddings[chunk["id"]] = cached_data["embedding"]
                    else:
                        # Cache miss -> request embedding
                        log.info("Embedding cache miss for chunk: %s. Fetching...", chunk["id"])
                        embedding = await self.get_embedding(chunk_text, api_key)
                        if embedding:
                            chunk_embeddings[chunk["id"]] = embedding
                            cache[chunk["id"]] = {
                                "hash": text_hash,
                                "embedding": embedding
                            }
                            cache_updated = True
                        else:
                            # Fallback if single API call fails
                            chunk_embeddings[chunk["id"]] = None

                if cache_updated:
                    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
                    with open(CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(cache, f)

                # Get query embedding
                query_embedding = await self.get_embedding(query, api_key)
                if query_embedding:
                    scores = []
                    for chunk in self.chunks:
                        emb = chunk_embeddings.get(chunk["id"])
                        if emb:
                            similarity = self.calculate_cosine_similarity(query_embedding, emb)
                            scores.append((chunk["id"], similarity))
                    
                    scores.sort(key=lambda x: x[1], reverse=True)
                    results = []
                    for cid, score in scores[:top_n]:
                        c = self.get_chunk_by_id(cid)
                        if c:
                            results.append(c)
                    log.info("[RAG RETRIEVAL] Vector search completed successfully.")
                    return results

            except Exception as ex:
                log.warning("Vector search failed: %s. Falling back to BM25 search.", ex)

        # Fallback to BM25 search
        log.info("[RAG RETRIEVAL] Executing BM25 search fallback.")
        bm25_scores = self.bm25.score_all(query)
        results = []
        for cid, score in bm25_scores[:top_n]:
            c = self.get_chunk_by_id(cid)
            if c:
                results.append(c)
        return results
