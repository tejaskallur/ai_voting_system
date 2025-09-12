import streamlit as st
from db import init_db, get_candidates, record_vote, get_votes
from voice_utils import listen, speak, list_microphones, test_microphone

st.set_page_config(page_title="AI Voting System", layout="wide")

# Initialize DB
init_db()

st.title("AI-driven Voting System — Prototype")
st.write("Voice-guided demo for blind-friendly voting (prototype).")

col1, col2 = st.columns([2,1])
with st.sidebar:
    st.header("Audio Settings")
    mics = list_microphones()
    selected_mic = st.selectbox("Input device", options=["Default"] + mics, index=0)
    prefer_vosk = st.toggle("Prefer Vosk (offline)", value=True)
    dynamic_energy = st.toggle("Auto energy threshold", value=True)
    energy = st.slider("Manual energy threshold", min_value=50, max_value=4000, value=300, step=50, disabled=dynamic_energy)
    st.markdown("---")
    # Stop flag for listening
    if "stop_listening" not in st.session_state:
        st.session_state.stop_listening = False
    def click_stop():
        st.session_state.stop_listening = True
    st.button("Stop Listening", on_click=click_stop)
    def _device_index():
        if selected_mic == "Default":
            return None
        try:
            return list_microphones().index(selected_mic)
        except ValueError:
            return None
    if st.button("Test Microphone (3s)"):
        with st.spinner("Testing mic..."):
            txt = test_microphone(seconds=3, device_index=_device_index(), energy_threshold=None if dynamic_energy else energy, dynamic_energy=dynamic_energy)
        if txt:
            st.success(f"Heard: {txt}")
        else:
            st.error("Did not capture any speech. Try raising threshold off or speak closer.")

with col1:
    st.header("Voting Console")
    if st.button("Start Voice Voting"):
        speak("Welcome. Please say your voter ID now.")
        voter = None
        try:
            with st.spinner("Listening for voter ID..."):
                device_index = _device_index()
                st.session_state.stop_listening = False
                voter = listen(prefer_vosk=prefer_vosk, device_index=device_index, should_stop=lambda: st.session_state.stop_listening, energy_threshold=None if dynamic_energy else energy, dynamic_energy=dynamic_energy)
                st.write(f"Debug - Heard: '{voter}'")
        except Exception as e:
            st.error(f"Audio error while capturing voter ID: {e}")
        if not voter or not voter.strip():
            speak("I could not capture your ID. Please try again.")
            st.error("Voter ID not captured. Try again.")
        else:
            st.success(f"Voter recognized: {voter}")
            candidates = get_candidates()
            speak("The candidates are as follows.")
            for cid, name in candidates:
                speak(f"Say {cid} for {name}.")
            speak("Please say the number of the candidate you choose.")
            choice = None
            try:
                with st.spinner("Listening for your choice..."):
                    device_index = _device_index()
                    st.session_state.stop_listening = False
                    choice = listen(prefer_vosk=prefer_vosk, device_index=device_index, should_stop=lambda: st.session_state.stop_listening, energy_threshold=None if dynamic_energy else energy, dynamic_energy=dynamic_energy)
                    st.write(f"Debug - Heard: '{choice}'")
            except Exception as e:
                st.error(f"Audio error while capturing choice: {e}")
            if not choice or not choice.strip():
                speak("Choice not heard. Please try again.")
                st.error("Could not capture candidate choice.")
            else:
                import re
                m = re.search(r"(\d+)", choice)
                if m:
                    cid = int(m.group(1))
                else:
                    cid = None
                    for id_, nm in candidates:
                        if nm.lower() in choice:
                            cid = id_
                            break
                if not cid:
                    speak("I could not understand the choice. Please try again.")
                    st.error(f"Unrecognized choice: {choice}")
                else:
                    cname = [n for i,n in candidates if i==cid]
                    cname = cname[0] if cname else str(cid)
                    speak(f"You selected {cname}. Say confirm to cast your vote or cancel to abort.")
                    conf = None
                    try:
                        with st.spinner("Listening for confirmation..."):
                            device_index = _device_index()
                            st.session_state.stop_listening = False
                            conf = listen(prefer_vosk=prefer_vosk, device_index=device_index, should_stop=lambda: st.session_state.stop_listening, energy_threshold=None if dynamic_energy else energy, dynamic_energy=dynamic_energy)
                            st.write(f"Debug - Heard: '{conf}'")
                    except Exception as e:
                        st.error(f"Audio error while capturing confirmation: {e}")
                    if conf and "confirm" in conf:
                        record_vote(voter, cid)
                        speak("Your vote has been recorded. Thank you for voting.")
                        st.success(f"Vote recorded for {cname}")
                    else:
                        speak("Vote cancelled or not confirmed.")
                        st.warning("Vote not recorded.")

with col2:
    st.header("Admin / Results")
    if st.button("Show Tally"):
        rows = get_votes()
        if not rows:
            st.info("No votes yet.")
        else:
            st.table(rows)
    st.markdown("---")
    st.markdown("**Notes**: This is a prototype. Use only demo voter IDs.")
