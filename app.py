import os
from dotenv import load_dotenv

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from groq import Groq
import psycopg

load_dotenv()


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL sozlanmagan.")

    return psycopg.connect(database_url, sslmode="require")


app = Flask(__name__)
UPLOAD_FOLDER = 'assets/images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# API kalitni muhit o'zgaruvchisidan o'qish
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Testlar bazasi (xotirada saqlash uchun)
tests_db = []


@app.route('/sitemap.xml')
def sitemap():
    from xml.etree.ElementTree import Element, SubElement, tostring

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = Element("urlset", xmlns=namespace)

    pages = [
        "https://sbs-ielts-examiner-2tsu.onrender.com/",
        "https://sbs-ielts-examiner-2tsu.onrender.com/index.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/skills/reading.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/skills/listening.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/skills/writing.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/skills/speaking.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/skills/full-mock.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/dashboard.html",
        "https://sbs-ielts-examiner-2tsu.onrender.com/login.html"
    ]

    for page in pages:
        url_element = SubElement(urlset, "url")
        SubElement(url_element, "loc").text = page

    xml = tostring(urlset, encoding="utf-8", xml_declaration=True)

    return app.response_class(xml, mimetype="application/xml")


def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tests (
                    id SERIAL PRIMARY KEY,
                    skill VARCHAR(50) NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    image_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()


# --- BOSHI SAHIFA ROUTI ---


@app.route('/')
def home():
    return render_template('skills/index.html')
from flask import send_from_directory

@app.route('/index.html')
def index_page():
    return render_template('skills/index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'assets/images'),
                               'logophoto.png', mimetype='image/png')

# Assets papkasidagi rasmlarni ochish
@app.route('/assets/<path:filename>')
def assets(filename):
    return send_from_directory(
        os.path.join(app.root_path, 'assets'),
        filename
    )

# --- ADMIN PANEL UCHUN YO'LLAR ---



@app.route('/api/add-test', methods=['POST'])
def add_test():
    try:
        skill = request.form.get('skill', '').strip()
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()

        if not skill or not title:
            return jsonify({
                "status": "error",
                "error": "Skill va test nomi kiritilishi shart."
            }), 400

        image_url = ""

        if 'file' in request.files:
            file = request.files['file']

            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                image_url = f"/assets/images/{filename}"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tests (skill, title, content, image_path)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (skill, title, content, image_url))

                test_id = cur.fetchone()[0]

        return jsonify({
            "status": "success",
            "message": "Test ma'lumotlar bazasiga saqlandi!",
            "id": test_id
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500




@app.route('/api/get-tests', methods=['GET'])
def get_tests():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, skill, title, content, image_path
                    FROM tests
                    ORDER BY id ASC
                """)
                rows = cur.fetchall()

        tests = [
            {
                "id": row[0],
                "skill": row[1],
                "title": row[2],
                "content": row[3] or "",
                "image": row[4] or ""
            }
            for row in rows
        ]

        return jsonify(tests)

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500




@app.route('/api/delete-test/<int:test_id>', methods=['DELETE'])
def delete_test(test_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tests WHERE id = %s RETURNING id",
                    (test_id,)
                )
                deleted_test = cur.fetchone()

        if deleted_test is None:
            return jsonify({
                "status": "error",
                "message": "Bunday test topilmadi."
            }), 404

        return jsonify({
            "status": "success",
            "message": "Test muvaffaqiyatli o'chirildi!"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# --- AI BAHOLASH UCHUN YO'L ---

@app.route('/api/ai-evaluate', methods=['POST'])
def ai_evaluate():
    try:
        data = request.get_json(silent=True) or {}

        task1_text = str(data.get('task1') or '').strip()
        task2_text = str(data.get('task2') or '').strip()

        if not task1_text and not task2_text:
            return jsonify({
                "success": False,
                "error": "Iltimos, Task 1 yoki Task 2 essayini kiriting."
            }), 400

        if not os.environ.get("GROQ_API_KEY"):
            return jsonify({
                "success": False,
                "error": "GROQ_API_KEY sozlanmagan. API kalitini muhit o'zgaruvchisiga kiriting."
            }), 500

        full_prompt = f"""
Evaluate the following IELTS Academic Writing responses using
the official IELTS Writing assessment criteria.

IMPORTANT RULES:
- Evaluate only the essay or essays that are provided.
- Do not invent information about a chart, graph, map or question.
- For Task 1, assess Task Achievement.
- For Task 2, assess Task Response.
- Assess Coherence and Cohesion, Lexical Resource, and
  Grammatical Range and Accuracy separately.
- Give a score from 0 to 9 in half-band increments for each
  criterion: for example, 5.0, 5.5, 6.0, 6.5, 7.0.
- Base every score on evidence in the student's actual writing.
- Do not give a high score simply because the essay is long
  or contains advanced vocabulary.
- Identify inaccurate data, missing overview, weak comparisons,
  unsupported arguments, repetition, grammar errors and
  unnatural word choices when applicable.
- Do not invent mistakes that are not present.
- Explain feedback in Uzbek, but preserve English examples.
- Be honest and consistent. Do not inflate scores.
- Distinguish between an estimated AI score and an official
  IELTS result.

TASK 1 ESSAY:
{task1_text if task1_text else "NOT PROVIDED"}

TASK 2 ESSAY:
{task2_text if task2_text else "NOT PROVIDED"}

Use this exact report structure in Markdown:

# IELTS Writing Evaluation

## Task 1
If Task 1 was provided:
| Criterion | Band | Explanation |
| Task Achievement | score | explanation |
| Coherence & Cohesion | score | explanation |
| Lexical Resource | score | explanation |
| Grammatical Range & Accuracy | score | explanation |

Give the estimated Task 1 band and explain the main reasons.
If Task 1 was not provided, write "Task 1 essay taqdim etilmadi."

## Task 2
If Task 2 was provided:
| Criterion | Band | Explanation |
| Task Response | score | explanation |
| Coherence & Cohesion | score | explanation |
| Lexical Resource | score | explanation |
| Grammatical Range & Accuracy | score | explanation |

Give the estimated Task 2 band and explain the main reasons.
If Task 2 was not provided, write "Task 2 essay taqdim etilmadi."

## Overall Writing Band
If both tasks were provided, estimate the combined Writing score.
Task 2 carries twice the weight of Task 1.
Calculate the average using the two task-level bands:
(Task 1 band + 2 * Task 2 band) / 3.
Round the result to the nearest half band, following IELTS-style
rounding. Show the unrounded calculation and the estimated final
band.

If only one task was provided, do not pretend to calculate a
complete IELTS Writing score. Report only the estimated band for
the submitted task.

## Main Strengths
List the three most important strengths.

## Main Problems
List the three most important weaknesses, with examples from
the essay wherever possible.

## Corrections
Show selected original phrases and their improved versions.
Do not rewrite the entire essay unless necessary.

## How to Improve
Give three specific, practical steps for reaching the next band.

Remember: IELTS Writing criteria are assessed separately.
Task 1 and Task 2 have different Task Achievement/Task Response
criteria. Be specific, evidence-based and fair.
"""

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a rigorous IELTS Academic Writing assessor. "
                        "Apply IELTS public band descriptors carefully. "
                        "Assess the submitted text, not an imagined essay. "
                        "Give criterion-specific evidence and realistic "
                        "estimated scores. Never claim to be an official "
                        "IELTS examiner or to provide an official result."
                    )
                },
                {
                    "role": "user",
                    "content": full_prompt
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.2,
            max_tokens=3500
        )

        ai_response = chat_completion.choices[0].message.content

        if not ai_response:
            return jsonify({
                "success": False,
                "error": "AI javobi bo'sh qaytdi. Qayta urinib ko'ring."
            }), 502

        return jsonify({
            "success": True,
            "feedback": ai_response
        })

    except Exception as e:
        app.logger.exception("IELTS evaluation error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/ai-evaluate-speaking', methods=['POST'])
def ai_evaluate_speaking():
    try:
        data = request.get_json(silent=True) or {}

        part1 = str(data.get('part1') or '').strip()
        part2 = str(data.get('part2') or '').strip()
        part3 = str(data.get('part3') or '').strip()
        audio_transcript = str(data.get('transcript') or '').strip()

        if not any([part1, part2, part3, audio_transcript]):
            return jsonify({
                "success": False,
                "error": "Iltimos, Speaking Part 1, Part 2 yoki Part 3 javobini kiriting."
            }), 400

        if not os.environ.get("GROQ_API_KEY"):
            return jsonify({
                "success": False,
                "error": "GROQ_API_KEY sozlanmagan. API kalitini tekshiring."
            }), 500

        full_prompt = f"""
You are assessing an IELTS Speaking practice response.

Assess the available responses using the four official IELTS
Speaking assessment criteria:

1. Fluency and Coherence
2. Lexical Resource
3. Grammatical Range and Accuracy
4. Pronunciation

Candidate responses:

PART 1:
{part1 if part1 else "NOT PROVIDED"}

PART 2:
{part2 if part2 else "NOT PROVIDED"}

PART 3:
{part3 if part3 else "NOT PROVIDED"}

Additional speech transcript, if available:
{audio_transcript if audio_transcript else "NOT PROVIDED"}

STRICT ASSESSMENT RULES:
- Explain the evaluation in Uzbek. Keep English examples unchanged.
- Give criterion scores from 0 to 9 in half-band increments.
- Base scores on evidence in the provided responses.
- Do not invent mistakes or claim the candidate said something
  that is absent from the supplied text.
- Evaluate grammar, vocabulary, relevance, development of ideas,
  and coherence using the available answers.
- Evaluate Fluency and Coherence cautiously if only written
  transcripts are available.
- Do not claim to have heard pronunciation from text.
- If no audio is supplied, mark Pronunciation as
  "Audio kerak" rather than inventing a score.
- If audio is not available to this endpoint, explicitly state
  that pronunciation, individual sounds, stress, and intonation
  cannot be reliably assessed from text alone.
- If only one Speaking part is provided, assess that part only.
  Do not pretend that one short answer represents a complete
  IELTS Speaking test.
- Give a realistic estimated score. This is practice feedback,
  not an official IELTS result.

Return the report in this structure:

# IELTS Speaking Evaluation

## 1. Fluency and Coherence
Band: [score or limited evidence]
- Kuchli tomonlar
- Kamchiliklar
- Matndan dalillar

## 2. Lexical Resource
Band: [score]
- Lug'at boyligi va so'z birikmalari
- Takrorlangan yoki noto'g'ri ishlatilgan so'zlar
- Yaxshilangan inglizcha variantlar

## 3. Grammatical Range and Accuracy
Band: [score]
- Grammatik xatolar
- Original phrase -> Corrected phrase
- Murakkab gaplardan foydalanish bo'yicha tavsiya

## 4. Pronunciation
- Audio mavjud bo'lsa, faqat haqiqatan eshitilgan dalillarga
  asoslanib bahola.
- Audio mavjud bo'lmasa, band qo'yma va audio kerakligini ayt.

## 5. Estimated Speaking Band
- Audio mavjud bo'lsa va barcha mezonlarni baholashga
  yetarli dalil bo'lsa, to'rtta mezonni hisobga olib
  taxminiy umumiy band ber.
- Audio bo'lmasa, faqat matn asosidagi taxminiy tahlilni ber.
  To'liq Speaking bandini ishonchli aniqlab bo'lmasligini ayt.

## 6. Main Strengths
Uchta asosiy kuchli tomon.

## 7. Main Problems
Uchta asosiy kamchilik va matndan dalillar.

## 8. Improved Answer
Nomzodning asosiy ma'nosini saqlagan holda tabiiyroq
inglizcha javob namunasi. Faqat taqdim etilgan savol va
javob ma'lumotlari bunga yetarli bo'lsa yoz.

## 9. How to Improve
Keyingi bandga chiqish uchun uchta aniq tavsiya.
"""

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a rigorous IELTS Speaking practice assessor. "
                        "Apply the four public IELTS Speaking criteria fairly. "
                        "Never invent audio evidence or pronunciation errors. "
                        "Distinguish text-based feedback from audio-based "
                        "assessment. Never claim to provide an official score."
                    )
                },
                {
                    "role": "user",
                    "content": full_prompt
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.2,
            max_tokens=3500
        )

        ai_response = chat_completion.choices[0].message.content

        if not ai_response:
            return jsonify({
                "success": False,
                "error": "AI javobi bo'sh qaytdi. Qayta urinib ko'ring."
            }), 502

        return jsonify({
            "success": True,
            "feedback": ai_response
        })

    except Exception as e:
        app.logger.exception("IELTS Speaking evaluation error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

from flask import abort

@app.route('/<page>.html')
def root_pages(page):
    allowed_pages = {'dashboard', 'login', 'admin'}

    if page not in allowed_pages:
        abort(404)

    return render_template(f'skills/{page}.html')


@app.route('/skills/<page>.html')
def skill_pages(page):
    allowed_pages = {
        'index',
        'full-mock',
        'reading',
        'listening',
        'writing',
        'speaking',
        'dashboard',
        'login',
        'admin'
    }

    if page not in allowed_pages:
        abort(404)

    return render_template(f'skills/{page}.html')



if __name__ == '__main__':
    try:
        init_db()
        print("PostgreSQL ulanishi va tests jadvali tayyor!")
    except Exception as e:
        print("Database xatosi:", e)

    app.run(debug=True, port=5000)
