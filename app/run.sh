#!/bin/bash

# Energy Insight - Startup Script

cd "$(dirname "$0")"

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt --quiet
else
    source venv/bin/activate
fi

# Run the Streamlit app
echo ""
echo "Starting Energy Insight..."
echo "The app will open in your browser at http://localhost:8501"
echo ""
streamlit run main.py --server.headless true
