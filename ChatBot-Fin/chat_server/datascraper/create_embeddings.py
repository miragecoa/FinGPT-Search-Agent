from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import openai
import pickle
import numpy as np
import faiss

# Initialize Flask app
app = Flask(__name__)

# OpenAI API key
load_dotenv()
api_key = os.getenv("API_KEY7")
openai.api_key = api_key

# Helper function to generate embeddings
def embed_file_content(file_content):
    """
    Function to send file content to OpenAI's embedding API and get embeddings.
    """
    response = openai.Embedding.create(
        input=file_content,
        model="text-embedding-ada-002"  # OpenAI's embedding model
    )
    return response['data'][0]['embedding']

# Helper function to store embeddings (pickling embeddings)
def store_embeddings(embeddings, file_paths):
    """
    Store the generated embeddings and file paths into a pickle file.
    """
    embeddings_data = {'file_paths': file_paths, 'embeddings': embeddings}
    with open('embeddings.pkl', 'wb') as f:
        pickle.dump(embeddings_data, f)

# Helper function to create a FAISS index
def create_faiss_index(embeddings):
    """
    Create and store a FAISS index from embeddings.
    """
    dimension = len(embeddings[0])  # Embedding dimension
    index = faiss.IndexFlatL2(dimension)  # L2 distance metric for similarity search

    # Convert embeddings to numpy array and add to FAISS index
    embeddings_np = np.array(embeddings).astype('float32')
    index.add(embeddings_np)

    # Store FAISS index to disk
    faiss.write_index(index, 'faiss_index.idx')

# API route to handle file paths and process the files
# @app.route('/api/upload_folder', methods=['POST'])
def upload_folder(file_paths):
    """
    API endpoint to receive file paths, process the files, generate embeddings,
    and store them.
    """

    embeddings = []
    file_contents = []

    # Process each file
    for file_path in file_paths:
        try:
            # Read file content (assuming text files for simplicity)
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Generate the embedding for this file's content
            embedding = embed_file_content(content)

            # Store the embedding and content for later use
            embeddings.append(embedding)
            file_contents.append(content)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue

    # Store embeddings and file paths
    store_embeddings(embeddings, file_paths)

    # Optionally, create and store a FAISS index
    create_faiss_index(embeddings)

    return jsonify({"message": "Files processed, embeddings stored, and FAISS index created."}), 200

# Start the Flask app
if __name__ == '__main__':
    app.run(debug=True)
