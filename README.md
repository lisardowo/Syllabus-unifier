# Syllabus Unifier

A student-built tool designed to simplify academic life by unifying course syllabi and schedules into easily digestible formats. Built during a hackathon with the theme "Make tools that help students."

## Overview

Syllabus Unifier extracts key information from multiple course syllabus PDFs and schedule documents, consolidating them into:
- A unified academic summary PDF with important dates, evaluation criteria, topics, resources, and instructor contact information
- A calendar file (.ics) for importing class schedules directly into Google Calendar or other calendar applications

## Features

- **Multi-document processing**: Upload multiple syllabus PDFs at once
- **Smart extraction**: Automatically detects and extracts:
  - Important dates (exams, deadlines, projects)
  - Evaluation criteria and grading breakdown
  - Course syllabus and topics
  - Instructor contact information
  - Course resources and bibliography
  - Special rules and policies
- **Schedule parsing**: Extracts class schedules from PDF documents
- **Calendar integration**: Generates .ics files for easy calendar import
- **Bilingual support**: Handles both English and Spanish content
- **Flexible date formats**: Recognizes various date and time formats

## Project Structure

```
Syllabus-unifier/
├── backend/              # FastAPI backend server
│   ├── main.py          # Main application with PDF processing logic
│   ├── requirements.txt # Python dependencies
│   └── README.md        # Backend setup instructions
├── HackPad/             # React frontend application
│   ├── src/             # React source code
│   ├── package.json     # Node.js dependencies
│   └── README.md        # Frontend setup instructions
├── node_modules/        # Node.js dependencies
├── package.json         # Root package configuration
└── README.md            # This file
```

## Prerequisites

- **Python 3.8+**: For running the backend server
- **Node.js 16+**: For running the frontend application
- **npm**: Node package manager

## Installation

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Frontend Setup

1. Navigate to the HackPad directory:
   ```bash
   cd HackPad
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

## Usage

### Starting the Backend

From the `backend/` directory (or from the root directory):

```bash
# Option A: From backend directory
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Option B: From root directory
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Verify the backend is running:
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

### Starting the Frontend

From the `HackPad/` directory:

```bash
cd HackPad
npm run dev
```

The frontend will be available at `http://localhost:5173`

### Using the Application

1. Open your browser and navigate to `http://localhost:5173`
2. Upload one or more syllabus PDF files
3. Optionally specify a semester start date for schedule generation
4. Click the generate button
5. Download the generated unified syllabus PDF and/or calendar .ics file

## API Endpoints

The backend provides the following endpoints:

- `GET /health` - Health check endpoint
- `POST /generar` - Generate unified syllabus PDF and schedule .ics (combined endpoint)
- `POST /syllabus` - Generate only the unified syllabus PDF
- `POST /schedule` - Generate only the class schedule .ics file

## Technologies Used

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **pypdf**: PDF reading and manipulation
- **reportlab**: PDF generation
- **pdfplumber**: Advanced PDF text extraction with positional data
- **ics**: Calendar file generation
- **uvicorn**: ASGI server

### Frontend
- **React**: UI library
- **Vite**: Build tool and development server
- **Axios**: HTTP client for API requests
- **React Dropzone**: File upload component

## Development

The project uses:
- CORS middleware to allow frontend-backend communication
- Support for multiple file uploads
- Regex-based pattern matching for extracting dates, times, and other information
- Positional text extraction for improved schedule detection
- Error handling and validation for robust processing

## Contributing

This project was built for students by students. Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests
- Improve documentation

## AI Tools Disclosure

This project was developed with the assistance of AI tools:

- **Gemini AI**: Used to generate and refine the prompts that were used to instruct GitHub Copilot during the development process. Gemini AI helped formulate clear, structured instructions for various coding tasks.

- **GitHub Copilot (GPT-5 model)**: Used as the primary coding assistant to implement features, write code, debug issues, and improve code quality based on the prompts generated with Gemini AI assistance.

The combination of these AI tools helped accelerate development while maintaining code quality and best practices. All AI-generated code was reviewed and validated by human developers.

## License

This project is open source and available for educational purposes.

## Acknowledgments

Built during a student hackathon focused on creating tools that make student life better. The project aims to reduce the time students spend manually organizing course information and schedules.
