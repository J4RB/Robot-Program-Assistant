# Robot Program Assistant

**Robot Program Assistant** is an AI-assisted robotics development tool developed as part of my MSc in Software Engineering thesis.

The project investigates how large language models (LLMs) can help developers understand, search, and modify existing robotic programs using natural language. The implemented prototype combines an agentic Retrieval-Augmented Generation (RAG) workflow with a searchable knowledge base of Universal Robots programs and technical documentation.

The goal is to make existing robotic solutions easier to understand and reuse, reducing the effort required to adapt automation applications.


## Features
- **Semantic program search**: Find relevant robot programs using natural-language queries.
- **AI-assisted program comprehension**: Ask questions about robot programs and receive explanations grounded in retrieved program data and technical documentation.
- **Agentic retrieval**: Dynamically select and invoke retrieval tools to gather relevant evidence before generating a response.
- **Program inspection and editing**: Inspect and edit robot program representations through a web-based editor.
- **Context-aware assistance**: Include the current program and recent conversation history when answering follow-up questions.
- **Program import and export workflows**: Load program data into the application and export robot programs in the `.urpx` format.
- **Source-aware responses**: Retain references to retrieved information used to generate answers.
- **Streaming progress updates**: Display intermediate assistant progress while longer requests are being processed.


## Technologies
- **Backend:** Python, FastAPI, LangChain, Pydantic
- **AI and retrieval:** Ollama, Qwen3.5, Qwen3 Embedding, Retrieval-Augmented Generation (RAG), agentic tool use
- **Data storage:** Qdrant, SQLite
- **Frontend:** React, React Router, Monaco Editor, JavaScript
- **Robotics:** Universal Robots, `.urpx` program files


## Architecture
The system consists of three main components.

### 1. Data Pipeline
An offline pipeline prepares the knowledge base for retrieval by transforming, chunking, embedding, and indexing robot programs and technical documentation.

The pipeline handles three types of information separately:

- **Program metadata**: High-level descriptions of robot applications and their components.
- **Program code**: Structured fragments extracted from Universal Robots `.urpx` programs.
- **Technical documentation**: Relevant passages extracted from PDF documentation.

The resulting embeddings are indexed in separate Qdrant collections.

### 2. Backend
A Python backend built with FastAPI coordinates the assistant workflow.

The retrieval process follows a ReAct-inspired, agentic approach: the language model can select from tools for searching program metadata, program code, and technical documentation. It evaluates the retrieved information and can perform additional retrieval steps before handing the collected evidence to a response-synthesis stage.

The final response combines the user's question, retrieved sources, relevant editor context, and recent conversation history.

### 3. Frontend
A React single-page application provides the user interface for searching programs, inspecting and editing program data, and interacting with the assistant.

The editor and chat interface allow users to ask questions in the context of the currently selected program. The frontend communicates with the backend through a REST API, with Server-Sent Events used to stream assistant progress.


## Evaluation
The prototype was evaluated through a controlled, within-subject user study comparing the proposed workflow with the baseline Universal Robots Studio workflow. Participants performed tasks involving both program comprehension and program modification.

The results were mixed:
- **Comprehension:**: Correctness remained near-perfect in both conditions, suggesting that the proposed workflow can support understanding of existing robot programs. However, comprehension tasks took longer with the proposed system. Much of the observed increase was associated with assistant latency and interaction overhead.
- **Modification:**: The proposed workflow performed worse than the baseline in both correctness and completion time, particularly for more structurally complex modifications.

The findings suggest that retrieval-supported LLM assistance is promising for robotic program comprehension, but reliable program modification requires better retrieval, broader domain coverage, and an editing workflow that works at a higher level of abstraction than raw program structures.


## Showcase
<p align="center"> 
  <img width="1920" height="1080" alt="search-tab" src="https://github.com/user-attachments/assets/7160e6a2-c9a6-4d4e-9887-7a4ea27bbadf" />
</p>

<p align="center"> 
  <img width="1920" height="1080" alt="edit-tab" src="https://github.com/user-attachments/assets/92a5839a-9be8-4b51-8972-a90e5479f244" />
</p>
