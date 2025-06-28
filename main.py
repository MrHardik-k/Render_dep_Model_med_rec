import os
import re
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
import pytesseract
import google.generativeai as genai

# Configure Gemini API
genai.configure(api_key="AIzaSyCuhh8OlesA16aGZbIkS_IbEycFOpx8gS0")
model = genai.GenerativeModel("gemini-2.0-flash")

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_UNITS = {"g/dL", "million/cmm", "%", "fL", "pg", "U/L", "/cmm", "µIU/mL",
                 "x10^3/µL", "mm/1hr", "ng/mL", "mg/dL", "mmol/L", "µmol/L", "IU/mL"}
LINE_RE = re.compile(r"^([A-Za-z][A-Za-z\s\-\(\)]+?)\s+([\d\.]+)\s*([A-Za-zµμ/%\^]+(?:/[A-Za-zµμ/%\^]+)?)")

# Utility: check file extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Utility: convert PDF to text
def ocr_pdf(path):
    pages = convert_from_path(path)
    return "".join(pytesseract.image_to_string(p) for p in pages)

# Utility: extract lab values
def extract_lab_values(txt):
    labs = {}
    for line in txt.splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        test, val, unit = m.groups()
        unit = unit.replace("μ", "µ")
        if unit not in ALLOWED_UNITS:
            continue
        try:
            val = float(val)
        except:
            continue
        test = re.sub(r"\b(Colorimetric|Calculated|Derived|Electrical impedance|Microscopic|Capillary photometry|H|L)\b", "", test, flags=re.I).strip()
        labs[test] = {"value": val, "unit": unit}
    return labs

# Route: PDF Upload and Summary Generation
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        text = ocr_pdf(filepath)
        labs = extract_lab_values(text)
        if not labs:
            return jsonify({"error": "No valid lab data found."}), 400

        prompt = "Clinical Summary:\n" + "\n".join(f"{k}: {v['value']} {v['unit']}" for k, v in labs.items())
        full_prompt = f"""
You are a medical assistant. Based on the following blood report, provide:
- Health Summary
- Possible Disease
- Is Critical (yes/no)
- Recommended Medicine
- Recommended Treatment

Report:
{prompt}
"""

        try:
            response = model.generate_content(full_prompt)
            return jsonify({"summary": response.text})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid file type"}), 400
