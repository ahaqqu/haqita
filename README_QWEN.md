# Qwen2-VL OCR for Product Promo Extraction

This tool uses Qwen2-VL (via Ollama) to intelligently extract product names and prices from promo images, solving the text grouping issues found in traditional OCR like PaddleOCR.

## Prerequisites

1. **Install Ollama**
   - Download and install from: https://ollama.com/download/windows
   - Ensure `ollama` is added to your system PATH

2. **Pull the Qwen2.5VL Model**
   Open a terminal and run:
   ```bash
   ollama pull qwen2.5vl
   ```
   *(Note: For higher accuracy on complex promos, you can use `qwen2.5vl:7b` if your VRAM allows)*

3. **Start Ollama Server**
   Keep this running in a separate terminal window:
   ```bash
   ollama serve
   ```

## Usage

1. **Place Images**: Put your promo images in the `data/logs/images/` folder.

2. **Run the Extractor**:
   Double-click `run_qwen_ocr.bat` or run via terminal:
   ```cmd
   run_qwen_ocr.bat
   ```

3. **View Results**:
   Extracted data will be saved to `output/product_prices.json`.

## Configuration

- **Model Selection**: Edit `qwen_ocr_processor.py` and change `MODEL_NAME = "qwen2-vl:2b"` to `qwen2-vl:7b` for better accuracy (requires ~6GB VRAM).
- **Input/Output Paths**: Modify `IMAGE_DIR` and `OUTPUT_FILE` in the Python script if needed.

## Requirements

- Python 3.8+
- `requests` library (`pip install requests`)
- NVIDIA GPU (RTX 4070 recommended for local inference)
