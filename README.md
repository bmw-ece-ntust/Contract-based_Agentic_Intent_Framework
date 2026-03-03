# Contract-based Agentic Intent Framework
This project provides a natural language refines to intent-based network intent contract using Large Language Models (LLMs).

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- curl (for testing API endpoints)

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv myenv
source myenv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Edit `setup_env.sh` with your API credentials:

```bash
export OPENAI_BASE_URL="<your-openai-base-url>"
export OPENAI_API_KEY="<your-openai-api-key>"

export OPENAI_BASE_UR_EVAL_="<your-openai-base-url>"
export OPENAI_API_KEY_EVAL="<your-openai-api-key>"
```

Then load the environment variables:

```bash
source setup_env.sh
```

## Running the Application

### Using Flask API Server

Start the Flask API server:

```bash
python main.py
```

#### Option 1: Using Streamlit UI 

Start the Streamlit web interface:

```bash
streamlit run streamlit_app.py
```


#### Option 2: Send requests using curl:

```bash
curl -X POST http://localhost:5200/human_language \
  -H "Content-Type: application/json" \
  -d '{"message": "<your intent>"}'
```


## Configuration

### LLM Model Settings

Edit `config.yaml` to customize the LLM parameters:

```yaml
  llm_model: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
  llm_temp: 0.6
  llm_top_p: 0.95
  llm_max_tokens: 65536
  message:
    - role: system
      content: "/think"
```


## Logs

Application logs are stored in the `logs/` directory:
- `logs/application.log` - Main application logs



## Citation

If you use NVIDIA Aerial™ CUDA-Accelerated RAN in your research, please cite:

```bibtex
@misc{bimo2026contractbasedagenticintentframework,
      title={Contract-based Agentic Intent Framework for Network Slicing in O-RAN}, 
      author={Fransiscus Asisi Bimo and Chun-Kai Lai and Zhi-Yuan Yang and Ray-Guang Cheng},
      year={2026},
      eprint={2603.01663},
      archivePrefix={arXiv},
      primaryClass={cs.NI},
      url={https://arxiv.org/abs/2603.01663}, 
}
```

