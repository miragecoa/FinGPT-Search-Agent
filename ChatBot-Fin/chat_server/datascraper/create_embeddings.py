from dotenv import load_dotenv
import os
import openai
import pickle
import numpy as np
import faiss
import json

# # Initialize Flask app
# app = Flask(__name__)

# OpenAI API key
load_dotenv()
api_key = os.getenv("API_KEY7")
openai.api_key = api_key

current_dir = os.path.dirname(os.path.abspath(__file__))
index_file = os.path.join(current_dir, 'faiss_index.idx')
embeddings_file = os.path.join(current_dir, 'embeddings.pkl')

# Helper function to generate embeddings
def embed_file_content(file_content):
    """
    Function to send file content to OpenAI's embedding API and get embeddings.
    """
    response = openai.Embedding.create(
        input=file_content,
        model="text-embedding-3-large"
    )
    return response['data'][0]['embedding']

# Helper function to store embeddings (pickling embeddings)
def store_embeddings(embeddings, file_paths):
    """
    Store the generated embeddings and file paths into a pickle file.
    """
    embeddings_data = {'file_paths': file_paths, 'embeddings': embeddings}
    with open(embeddings_file, 'wb') as f:
        pickle.dump(embeddings_data, f)

# Helper function to create a FAISS index
def create_faiss_index(embeddings):
    """
    Create and store a FAISS index from embeddings.
    """
    dimension = len(embeddings[0])  # Embedding dimension
    index = faiss.IndexFlatL2(dimension)  # L2 distance metric for similarity search
    print("Creating index with dimension:", dimension)

    # Convert embeddings to numpy array and add to FAISS index
    embeddings_np = np.array(embeddings).astype('float32')
    index.add(embeddings_np)
    print("Embeddings numpy shape:", embeddings_np.shape)

    print(type(embeddings))
    print(len(embeddings))
    print(type(embeddings[0]))
    print(len(embeddings[0]))

    # Store FAISS index to disk
    faiss.write_index(index, index_file)

def upload_folder(data):
    """
    Function to process files that can be called directly from other code
    """
    try:
        print("[DEBUG] Starting upload_folder with files:", len(data))
        
        embeddings = []
        file_contents = []
        print("[DEBUG] data: ", data)
        files = data.get('filePaths')

        # Process each file content
        for file in files:
            try:
                print("[DEBUG] file: ", file)
                file_name = file.get('name')
                file_content = file.get('content')
                print("[DEBUG] name: ", file_name)
                print("[DEBUG] content length: ", len(file_content) if file_content else None)

                if file_name and file_content:
                    # Generate embedding and store file content for processing
                    embedding = embed_file_content(file_content)
                    print("[DEBUG] embedding: ", embedding)
                    embeddings.append(embedding)
                    file_contents.append(file_content)
            except Exception as e:
                print(f"[DEBUG] Error processing file: {str(e)}")
                continue

        # Store embeddings and file paths
        store_embeddings(embeddings, [f.get('name') for f in files])
        print("[DEBUG] embeddings stored")

        # Create and store a FAISS index
        create_faiss_index(embeddings)
        print("[DEBUG] FAISS index created")

        return {"message": "Files processed, embeddings stored, and FAISS index created."}, 200
    
    except Exception as e:
        print(f"[DEBUG] Unexpected error in upload_folder: {str(e)}")
        return {"error": f"Server error: {str(e)}"}, 500

# # Start the Flask app
# if __name__ == '__main__':
#     app.run(debug=True)
