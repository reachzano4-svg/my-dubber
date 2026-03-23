import streamlit as st
import asyncio, edge_tts, srt, os, re, pandas as pd
from pydub import AudioSegment
from deep_translator import GoogleTranslator
from audiostretchy.stretch import stretch_audio
import streamlit as st

# --- កំណត់ឈ្មោះអ្នកប្រើ និង លេខសម្ងាត់ ---
USER_NAME = "admin"
USER_PASSWORD = "reachzano" # បងប្តូរលេខសម្ងាត់នៅទីនេះ

def login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.subheader("🔐 សូមចូលប្រើប្រាស់ប្រព័ន្ធ")
        user = st.text_input("ឈ្មោះអ្នកប្រើ (Username)")
        pw = st.text_input("លេខសម្ងាត់ (Password)", type="password")
        
        if st.button("ចូលប្រើ (Login)", use_container_width=True):
            if user == USER_NAME and pw == USER_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("ឈ្មោះ ឬ លេខសម្ងាត់មិនត្រឹមត្រូវ!")
        st.stop() # បញ្ឈប់កូដខាងក្រោមមិនឱ្យដើរ បើមិនទាន់ Login

# ហៅ Function Login មកប្រើនៅខាងលើគេបង្អស់
login()

# --- បន្ទាប់មកគឺជាកូដចាស់របស់បង (st.set_page_config...) ---
# --- ១. Helper Functions (ចាប់ភេទឆ្លាត និងបកប្រែសម្រាយ) ---
def localize_khmer(text):
    if not text: return ""
    slang_map = {
        r"តើ(.*)មែនទេ": r"\1មែនអត់?", r"តើ(.*)ឬទេ": r"\1អត់?", 
        r"អ្នក": "ឯង", r"បាទ": "ហ្នឹងហើយ", r"ចាស": "ចា៎",
        r"សម្លៀកបំពាក់": "ខោអាវ", r"តើមានរឿងអ្វី": "មានរឿងអីហ្នឹង?", r"មិនអីទេ": "អត់អីទេ"
    }
    for p, r in slang_map.items(): text = re.sub(p, r, text)
    return re.sub(r"^តើ\s*", "", text).strip()

def get_voice_auto(text):
    text = str(text)
    f_words = ["ចាស", "ចា៎", "អូន", "នាង", "ម៉ាក់", "យាយ", "មីង", "កញ្ញា", "ស្រី", "ប្រពន្ធ", "ភរិយា", "អ្នកគ្រូ"]
    m_words = ["បាទ", "បាទបង", "ខ្ញុំបាទ", "លោក", "ពូ", "តា", "បងប្រុស", "ប៉ា", "លោកគ្រូ", "លោកម្ចាស់", "ទូលបង្គំ"]
    if any(w in text for w in f_words): return "Female"
    if "បង" in text and not any(w in text for w in ["បងស្រី", "ប្អូនស្រី", "អូន"]): return "Male"
    if any(w in text for w in m_words): return "Male"
    return "Male"

# --- ២. Audio Engine (ដើរទាំងលើ PC និង Cloud) ---
async def process_audio(data, speed, status, progress):
    combined = AudioSegment.silent(duration=0)
    current_ms = 0
    for i, row in enumerate(data):
        progress.progress((i + 1) / len(data))
        status.markdown(f"**🎙️ ផលិតឃ្លាទី:** `{i+1}`")
        text, duration = str(row['Khmer_Text']).strip(), (row['End'] - row['Start']).total_seconds() * 1000
        start_ms = row['Start'].total_seconds() * 1000
        
        if start_ms > current_ms:
            combined += AudioSegment.silent(duration=start_ms - current_ms)
            current_ms = start_ms
            
        v = "km-KH-SreymomNeural" if row['Voice'] == "Female" else "km-KH-PisethNeural"
        tmp = f"t_{i}.mp3"
        await edge_tts.Communicate(text, v, rate=f"{speed+20:+}%").save(tmp)
        
        if os.path.exists(tmp):
            seg = AudioSegment.from_file(tmp)
            wav = f"t_{i}.wav"; seg.export(wav, format="wav")
            if len(seg) > duration > 0:
                stretch_audio(wav, f"s_{i}.wav", min(len(seg)/duration, 1.3))
                seg = AudioSegment.from_file(f"s_{i}.wav")
            combined += seg; current_ms += len(seg)
            for f in [tmp, wav, f"s_{i}.wav"]: 
                if os.path.exists(f): 
                    try: os.remove(f)
                    except: pass
    return combined

# --- ៣. UI Layout ---
st.set_page_config(page_title="Reach Dubber Pro", layout="wide", initial_sidebar_state="collapsed")
st.title("🎬 Smart AI Dubbing (PC & Mobile)")

if 'data' not in st.session_state: st.session_state.data = None
if 'audio' not in st.session_state: st.session_state.audio = None

# --- SIDEBAR (Settings & Find/Replace) ---
with st.sidebar:
    st.header("⚙️ ការកំណត់")
    speed = st.slider("ល្បឿនសម្លេង AI (%)", -50, 50, 15)
    bgm = st.file_uploader("ភ្លេងផ្ទៃក្រោយ (BGM)", type=["mp3"])
    vol = st.slider("កម្រិតសម្លេង BGM", 0, 100, 15)
    
    st.divider()
    st.subheader("🔍 Find & Replace (ប្តូរអត្ថបទ)")
    f_txt = st.text_input("ស្វែងរកពាក្យ:", key="sb_find")
    r_txt = st.text_input("ជំនួសដោយ:", key="sb_replace")
    
    ck, ce = st.columns(2)
    if ck.button("🇰🇭 ប្តូរក្នុងខ្មែរ", use_container_width=True):
        if st.session_state.data and f_txt:
            df_tmp = pd.DataFrame(st.session_state.data)
            df_tmp['Khmer_Text'] = df_tmp['Khmer_Text'].astype(str).str.replace(f_txt, r_txt, case=False, regex=True)
            st.session_state.data = df_tmp.to_dict('records'); st.rerun()

    if ce.button("🇺🇸 ប្តូរក្នុង EN", use_container_width=True):
        if st.session_state.data and f_txt:
            df_tmp = pd.DataFrame(st.session_state.data)
            df_tmp['English'] = df_tmp['English'].astype(str).str.replace(f_txt, r_txt, case=False, regex=True)
            st.session_state.data = df_tmp.to_dict('records'); st.rerun()

    if st.button("🔴 Reset Project", use_container_width=True): 
        st.session_state.data = None; st.session_state.audio = None; st.rerun()

# --- MAIN PAGE ---
file = st.file_uploader("Upload Subtitle (.srt)", type=["srt"])
if file and st.session_state.data is None:
    if st.button("🔍 Step 1: ចាប់ផ្តើមបកប្រែ", type="primary"):
        subs = list(srt.parse(file.getvalue().decode("utf-8")))
        tr_en, tr_km = GoogleTranslator(source='auto', target='en'), GoogleTranslator(source='en', target='km')
        data = []
        p = st.progress(0)
        for i, s in enumerate(subs):
            en = tr_en.translate(s.content)
            km = localize_khmer(tr_km.translate(en))
            data.append({
                "ID": i, "Select": False, "Original": s.content, "English": en, 
                "Khmer_Text": km, "Voice": get_voice_auto(km), "Start": s.start, "End": s.end
            })
            p.progress((i+1)/len(subs))
        st.session_state.data = data; st.rerun()

if st.session_state.data:
    st.subheader("📝 ផ្ទៀងផ្ទាត់ និងកែសម្រួល")
    df = pd.DataFrame(st.session_state.data)
    
    # ប៊ូតុងបញ្ជាភេទ និងបកប្រែឡើងវិញ
    c1, c2, c3, c4 = st.columns([1,1,1,1.5])
    with c1:
        if st.button("👩 ស្រី (រើស)", use_container_width=True):
            edited_rows = st.session_state.get("stable_editor", {}).get("edited_rows", {})
            for idx, val in edited_rows.items():
                if val.get("Select") == True or df.iloc[idx]["Select"] == True: df.at[idx, "Voice"] = "Female"
            st.session_state.data = df.to_dict('records'); st.rerun()
    with c2:
        if st.button("👨 ប្រុស (រើស)", use_container_width=True):
            edited_rows = st.session_state.get("stable_editor", {}).get("edited_rows", {})
            for idx, val in edited_rows.items():
                if val.get("Select") == True or df.iloc[idx]["Select"] == True: df.at[idx, "Voice"] = "Male"
            st.session_state.data = df.to_dict('records'); st.rerun()
    with c3:
        if st.button("👔 ប្រុសទាំងអស់", use_container_width=True):
            df['Voice'] = 'Male'; st.session_state.data = df.to_dict('records'); st.rerun()
    with c4:
        if st.button("♻️ Fix Selected", use_container_width=True):
            tr_km_fix = GoogleTranslator(source='en', target='km')
            for idx, row in df.iterrows():
                if row['Select'] == True:
                    try: df.at[idx, 'Khmer_Text'] = localize_khmer(tr_km_fix.translate(row['English']))
                    except: pass
            st.session_state.data = df.to_dict('records'); st.rerun()

    # តារាង Editor (Stable Mode)
    edited_df = st.data_editor(
        df, key="stable_editor", use_container_width=True, hide_index=True,
        column_config={
            "ID": None, "Start": None, "End": None,
            "Select": st.column_config.CheckboxColumn("✔", default=False),
            "Original": st.column_config.TextColumn("CH", disabled=True),
            "English": st.column_config.TextColumn("EN Ref", width="medium"),
            "Khmer_Text": st.column_config.TextColumn("Khmer (កែនៅទីនេះ)", width="large"),
            "Voice": st.column_config.SelectboxColumn("ភេទ", options=["Male", "Female"])
        }
    )

    if st.button("💾 រក្សាទុកការកែ (Save Changes)", type="primary", use_container_width=True):
        st.session_state.data = edited_df.to_dict('records'); st.success("បានរក្សាទុក!")

    st.divider()
    if st.button("🚀 ផលិតសម្លេង (Dub Now)", use_container_width=True):
        stat = st.empty(); pb = st.progress(0)
        try:
            res = asyncio.run(process_audio(st.session_state.data, speed, stat, pb))
            if bgm:
                b_s = AudioSegment.from_file(bgm) - (60 - (vol * 0.6))
                if len(b_s) < len(res): b_s = b_s * (int(len(res)/len(b_s)) + 1)
                res = res.overlay(b_s[:len(res)])
            res.export("out.mp3", format="mp3")
            with open("out.mp3", "rb") as f: st.session_state.audio = f.read()
            st.success("ផលិតរួចរាល់!")
        except Exception as e: st.error(f"Error: {e}")

    if st.session_state.audio:
        st.audio(st.session_state.audio)
        st.download_button("📥 ទាញយក MP3", st.session_state.audio, "dub_final.mp3", use_container_width=True)
