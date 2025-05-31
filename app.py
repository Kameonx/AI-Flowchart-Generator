import os
from flask import Flask, render_template_string, request, jsonify
import re, requests
import io
import base64
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
VENICE_API_KEY = os.getenv("VENICE_API_KEY")
CHAT_MODEL = "llama-3.3-70b"

# CSS for dark theme (existing styles)
CSS = """
body {
    background: #121212;
    color: white;
    font-family: Arial, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 0;
}

#flowchart {
    margin-top: 50px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    width: 80%;
    align-items: center; /* center bubbles horizontally */
}

.bubble {
    background: #2d2d2d;
    border-radius: 15px;
    padding: 20px;
    min-width: 300px;
    max-width: 90vw;
    width: auto;
    position: relative;
    color: white;
    margin: 0 auto;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    word-break: break-word;
    overflow-wrap: break-word;
    white-space: pre-line;
}

.bubble strong {
    word-break: break-word;
}

.bubble:not(:last-child)::after {
    content: '↓';
    display: flex;
    justify-content: center;
    align-items: center;
    text-align: center;
    margin: 10px 0;
    color: #50fa7b;
    font-size: 24px;
    width: 100%;
}

.sub-bubble {
    background: #404040;
    margin-left: 30px;
    border-radius: 10px;
    padding: 10px;
    margin-top: 10px;
    width: auto;
    max-width: 80vw;
    box-sizing: border-box;
    word-break: break-word;
    overflow-wrap: break-word;
    white-space: pre-line;
}

input[type=text], textarea {
    width: 80%;
    padding: 15px;
    margin: 20px 0;
    background: #2d2d2d;
    color: white;
    border: none;
    border-radius: 8px;
}

button {
    padding: 12px 30px;
    background: #50fa7b;
    color: black;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    transition: 0.3s;
}

button:hover {
    background: #50fa7b;
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

#flowchart-text {
    margin-top: 40px;
    max-width: 800px;
    background: #232323;
    border-radius: 12px;
    padding: 20px;
    color: #50fa7b;
    font-family: monospace;
    white-space: pre-wrap;
    display: flex;
    justify-content: center;
    align-items: center;
    margin-left: auto;
    margin-right: auto;
    width: fit-content;
    min-width: 200px;
    box-sizing: border-box;
    text-align: center;
}
"""

# HTML template
HTML = f"""
<!DOCTYPE html>
<html>
<head>
  <title>Flowchart Generator</title>
  <style>{CSS}</style>
</head>
<body>
  <h1 style="color: #50fa7b; margin-top: 30px;">Flowchart Generator</h1>
  <textarea id="input" rows="15" placeholder="Enter your flowchart text here..." style="resize: none;"></textarea>
  <button onclick="generateFlowchart()">Generate Flowchart</button>
  <div id="loading" style="display:none; color:#50fa7b; margin-top:20px; font-size:20px;">Generating, please wait...</div>
  <div id="flowchart-image-container" style="margin-top:40px; display:flex; justify-content:center;"></div>
<script>
function generateFlowchart() {{
    document.getElementById('loading').style.display = 'block';
    fetch('/generate', {{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{text: document.getElementById('input').value}})
    }})
    .then(r=>r.json())
    .then(data=>{{
        document.getElementById('loading').style.display = 'none';
        // show generated flowchart as image if available
        const imgDiv = document.getElementById('flowchart-image-container');
        if(data.flowchart_text) {{
            fetch('/text-to-image', {{
                method: 'POST',
                headers: {{'Content-Type':'application/json'}},
                body: JSON.stringify({{text: data.flowchart_text}})
            }})
            .then(r=>r.json())
            .then(imgData => {{
                if(imgData.image_url) {{
                    imgDiv.innerHTML = `<img src="${{imgData.image_url}}" style="max-width:800px; border-radius:12px; background:#232323; padding:20px; display:block; margin:auto;" alt="Flowchart Image">`;
                }} else {{
                    imgDiv.innerHTML = '<div style="color:#ff5555;">Could not render image.</div>';
                }}
            }});
        }} else {{
            imgDiv.innerHTML = '';
        }}
        // show error if present
        if(data.error) {{
            imgDiv.innerHTML = `<div style="color:#ff5555; margin-top:20px;">Error: ${{data.error}}</div>`;
        }}
    }})
    .catch(err => {{
        document.getElementById('loading').style.display = 'none';
        document.getElementById('flowchart-image-container').innerHTML = '<div style="color:#ff5555; margin-top:20px;">An error occurred. Please try again.</div>';
    }});
}}
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    text = data.get('text', '')
    # Parse sections for display (used for flow_desc)
    parsed_lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    sections_for_desc = []
    cur_section = None
    for line_content in parsed_lines:
        m = re.match(r'^(\d+\.)\s+(.*)', line_content)
        sm = re.match(r'^(\d+\.\d+)\s+(.*)', line_content)
        bm = re.match(r'^[-*]\s+(.*)', line_content)
        if m:
            if cur_section: sections_for_desc.append(cur_section)
            cur_section = {'header': f"{m.group(1)} {m.group(2)}", 'items': []}
        elif sm and cur_section:
            cur_section['items'].append(f"{sm.group(1)} {sm.group(2)}")
        elif bm and cur_section:
            cur_section['items'].append(bm.group(1))
        elif cur_section:
            cur_section['items'].append(line_content)
    if cur_section: sections_for_desc.append(cur_section)

    # Build a flow description for the chat model
    if sections_for_desc:
        flow_desc = ''
        for idx, s in enumerate(sections_for_desc):
            flow_desc += f"- {s['header']}\n"
            for i in s['items']:
                flow_desc += f"  - {i}\n"
            if idx < len(sections_for_desc) - 1:
                flow_desc += "  ↓ (Next main step)\n" 
    else:
        flow_desc = text.strip()

    try:
        flowchart_text_from_ai = get_flowchart_text(flow_desc)
        
        cleaned_text = re.sub(r'(\*+)', '', flowchart_text_from_ai)
        cleaned_text = re.sub(r'^\s*[\*\-]\s+', '', cleaned_text, flags=re.MULTILINE)
        cleaned_text = re.split(r'\n\s*Note:|\n\s*note:', cleaned_text, flags=re.IGNORECASE)[0].strip()

        lines_from_ai = cleaned_text.split('\n')
        output_formatted_lines = []
        
        current_line_index = 0
        while current_line_index < len(lines_from_ai):
            line_text_content = lines_from_ai[current_line_index].strip()
            if not line_text_content:
                current_line_index += 1
                continue

            is_main_point = re.match(r'^\d+\.\s', line_text_content)
            
            if is_main_point:
                main_point_text = line_text_content
                main_point_visual_width = len(main_point_text) + 4  # Add padding inside box
                
                # Create box with sides (remove right side wall)
                box_width = main_point_visual_width + 1  # Total width including the left character
                output_formatted_lines.append("┌" + "─" * (main_point_visual_width))
                
                # Properly center the main point within the entire box width 
                spaces_needed = box_width - len(main_point_text)
                left_padding = spaces_needed // 2
                output_formatted_lines.append(" " + " " * left_padding + main_point_text)
                
                # Process sub-points - keep the left vertical bar only for these
                sub_points_start_index = current_line_index + 1
                temp_sub_point_index = sub_points_start_index
                while temp_sub_point_index < len(lines_from_ai):
                    possible_sub_point = lines_from_ai[temp_sub_point_index].strip()
                    if not possible_sub_point: # Skip empty lines
                        temp_sub_point_index +=1
                        continue
                    if re.match(r'^\d+\.\s', possible_sub_point): # Next main point found
                        break
                    
                    # Add sub-points inside the box, left aligned (with left vertical bar)
                    indented_point = "  • " + possible_sub_point
                    padding = " " * (main_point_visual_width - len(indented_point))
                    output_formatted_lines.append("│ " + indented_point + padding)
                    temp_sub_point_index += 1
                
                # Bottom border of the box
                output_formatted_lines.append("└" + "─" * (main_point_visual_width))
                current_line_index = temp_sub_point_index # Update main index

                # Check for a subsequent main point to add an arrow
                another_main_point_follows = False
                for look_ahead_index in range(current_line_index, len(lines_from_ai)):
                    if lines_from_ai[look_ahead_index].strip() and re.match(r'^\d+\.\s', lines_from_ai[look_ahead_index].strip()):
                        another_main_point_follows = True
                        break
                
                # Use only one arrow between containers
                if another_main_point_follows:
                    # Use box width to determine center position for arrow
                    output_formatted_lines.append("")  # Empty line before arrow
                    output_formatted_lines.append(" " * (box_width//2) + "↓" + " " * (box_width//2))
                    output_formatted_lines.append("")  # Empty line after arrow
            else:
                # Fallback for lines that are not main points
                output_formatted_lines.append("    " + line_text_content)
                current_line_index += 1
        
        final_text_for_image = '\n'.join(output_formatted_lines)
        return jsonify(flowchart_text=final_text_for_image)
    except Exception as e:
        return jsonify(flowchart_text="", error=str(e)), 500

def get_flowchart_text(desc):
    # Use Venice chat endpoint to generate a detailed flowchart in text
    h = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
    p = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a flowchart expert. Given a structured flow description, generate ONLY the flowchart in text form, with no extra commentary, notes, or explanations. "
                    "Include all nodes, steps, and relationships exactly as described by the user. "
                    "Use a clear, readable format with numbered main points (e.g., '1. Step One') and indented sub-points (e.g., '  - Sub-step 1.1'). "
                    "Do NOT use markdown like asterisks for bolding or italics. Do NOT add any summary, notes, or explanations after the flowchart."
                )
            },
            {"role": "user", "content": desc}
        ]
    }
    resp = requests.post("https://api.venice.ai/api/v1/chat/completions", headers=h, json=p)
    resp_json = resp.json()
    if 'choices' not in resp_json or not resp_json['choices']:
        raise Exception(f"Venice API error: {resp_json.get('error', 'No choices returned')}")
    return resp_json['choices'][0]['message']['content']

@app.route('/text-to-image', methods=['POST'])
def text_to_image():
    data = request.get_json()
    text = data.get('text', '') 

    normal_font_size = 18
    main_point_font_size = 22  # Bigger font for main points

    font_dir = os.path.dirname(__file__)
    dejavu_font_path = os.path.join(font_dir, "DejaVuSans.ttf")
    dejavu_bold_font_path = os.path.join(font_dir, "DejaVuSans-Bold.ttf")

    try:
        # Try bundled DejaVu fonts first (for server)
        normal_font = ImageFont.truetype(dejavu_font_path, normal_font_size)
        try:
            bold_font = ImageFont.truetype(dejavu_bold_font_path, main_point_font_size)
        except Exception:
            bold_font = ImageFont.truetype(dejavu_font_path, main_point_font_size)
    except Exception:
        try:
            # Fallback to Arial (for local host)
            normal_font = ImageFont.truetype("arial.ttf", normal_font_size)
            try:
                bold_font = ImageFont.truetype("arialbd.ttf", main_point_font_size)
            except Exception:
                bold_font = ImageFont.truetype("arial.ttf", main_point_font_size)
        except Exception:
            # Final fallback: PIL default font
            normal_font = ImageFont.load_default()
            bold_font = ImageFont.load_default()
    
    lines = text.split('\n')
    padding = 20
    line_spacing = 6 

    # First pass to calculate dimensions
    max_text_width = 0
    total_text_height = 0
    dummy_img = Image.new("RGB", (1,1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    # Keep track of line heights for each line based on its font
    line_heights = []

    for line in lines:
        # Determine if this is a main point line (it's between box top and bottom lines)
        is_main_point_text = False
        if line and not line.startswith("┌") and not line.startswith("└") and not line.startswith("│") and not "─" in line and not "↓" in line:
            # This is likely a main point text (centered text without box characters)
            is_main_point_text = True
            font_to_use = bold_font
        else:
            font_to_use = normal_font
        
        try:
            bbox = dummy_draw.textbbox((0,0), line, font=font_to_use)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            bbox = dummy_draw.textbbox((0,0), line, font=font_to_use)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            
        if w > max_text_width:
            max_text_width = w
        total_text_height += h + line_spacing
        line_heights.append((h, font_to_use, is_main_point_text))
    
    if not lines: 
        total_text_height = normal_font_size 

    # Cap image width to prevent excessively large images
    img_width = int(min(max_text_width + 2 * padding, 1800)) 
    img_height = int(total_text_height - line_spacing + 2 * padding) 

    img_width = max(img_width, 200) 
    img_height = max(img_height, normal_font_size + 2 * padding)

    img = Image.new("RGB", (img_width, img_height), color=(35,35,35))
    draw = ImageDraw.Draw(img)
    
    current_y = padding
    for idx, line in enumerate(lines):
        height, font_to_use, is_main_point = line_heights[idx]
        
        try:
            bbox = draw.textbbox((0,0), line, font=font_to_use)
            line_width = bbox[2] - bbox[0]
        except AttributeError:
            bbox = draw.textbbox((0,0), line, font=font_to_use)
            line_width = bbox[2] - bbox[0]

        # Calculate position for center-aligned elements
        if "─" in line or "┌" in line or "└" in line or "┐" in line or "┘" in line or "↓" in line:
            # Center boxes and arrows
            x_position = (img_width - line_width) / 2
        else:
            # For text lines (inside boxes)
            x_position = (img_width - max_text_width) / 2

        # Use a different color for main points to make them stand out more
        text_color = (120, 255, 140) if is_main_point else (80, 250, 123)
        draw.text((x_position, current_y), line, font=font_to_use, fill=text_color)
        current_y += height + line_spacing

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return jsonify(image_url=f"data:image/png;base64,{img_b64}")

if __name__ == '__main__':
    app.run(debug=True)
