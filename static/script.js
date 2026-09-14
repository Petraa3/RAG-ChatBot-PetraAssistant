const chatWindow = document.getElementById("chat-window");
const composer = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const uploadBtn = document.getElementById("upload-btn");
const fileInput = document.getElementById("file-input");
const filePreviewContainer = document.getElementById("file-preview");

let selectedFile = null;

/**
 * Menambahkan elemen pesan baru ke antarmuka chat
 */
function addMessage(role, text, isError = false) {
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;

  // 1. Elemen Avatar Icon
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.innerHTML = role === "user" 
    ? '<i class="fa-solid fa-user"></i>' 
    : '<i class="fa-solid fa-sparkles"></i>';

  // 2. Wrapper untuk Nama & Bubble
  const wrapper = document.createElement("div");
  wrapper.className = "bubble-wrapper";

  // Nama Pengirim
  const senderName = document.createElement("span");
  senderName.className = "sender-name";
  senderName.textContent = role === "user" ? "Anda" : "Petra Assistant";

  // Balon Pesan (Bubble)
  const bubble = document.createElement("div");
  bubble.className = "bubble" + (isError ? " error" : "");

  // Render Markdown menggunakan marked.js jika balasan dari assistant
  if (role === "assistant" && !isError && typeof marked !== "undefined") {
    bubble.innerHTML = marked.parse(text);
  } else {
    bubble.textContent = text;
  }

  // Menyusun struktur elemen
  wrapper.appendChild(senderName);
  wrapper.appendChild(bubble);

  msg.appendChild(avatar);
  msg.appendChild(wrapper);

  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  return bubble;
}

// #---animasi loading------
function addLoadingBubble() {
  const msg = document.createElement("div");
  msg.className = "msg assistant";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.innerHTML = '<i class="fa-solid fa-sparkles"></i>';

  const wrapper = document.createElement("div");
  wrapper.className = "bubble-wrapper";

  const senderName = document.createElement("span");
  senderName.className = "sender-name";
  senderName.textContent = "Petra Assistant";

  const bubble = document.createElement("div");
  bubble.className = "bubble loading";
  bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

  wrapper.appendChild(senderName);
  wrapper.appendChild(bubble);

  msg.appendChild(avatar);
  msg.appendChild(wrapper);

  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  return msg;
}

/**
 * Mengirim pesan teks ke backend /api/chat
 */
async function sendMessage(text) {
  addMessage("user", text);
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  const loadingMsg = addLoadingBubble();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    const data = await res.json();
    loadingMsg.remove();

    if (!res.ok || data.error) {
      addMessage("assistant", data.error || "Terjadi kesalahan saat memproses permintaan.", true);
    } else {
      addMessage("assistant", data.answer);
    }
  } catch (err) {
    loadingMsg.remove();
    addMessage("assistant", "Gagal menghubungi server. Pastikan server aplikasi (app.py) sedang berjalan.", true);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

// upload file dan kirim pertanyaan ke backend /api/upload
async function processUploadAndSend(file, textQuery) {
  uploadBtn.disabled = true;
  uploadBtn.classList.add("uploading");
  if (textQuery) {
    addMessage("user", `[Lampiran: ${file.name}]\n\n${textQuery}`);
  } else {
    addMessage("user", `[Mengunggah Dokumen: ${file.name}]`);
  }

  input.value = "";
  input.style.height = "auto";
  cancelFileSelection();

  const loadingMsg = addLoadingBubble();

  const formData = new FormData();
  formData.append("file", file);

  try {
    // 1. Upload & Indeks File ke Backend
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      loadingMsg.remove();
      addMessage("assistant", data.error || "Gagal mengupload dokumen.", true);
      return;
    }

    addMessage("assistant", `📄 ${data.message}`);

    // 2. Jika ada teks pertanyaan dari user, tanyakan langsung ke RAG
    if (textQuery) {
      const chatRes = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: textQuery }),
      });

      const chatData = await chatRes.json();
      loadingMsg.remove();

      if (!chatRes.ok || chatData.error) {
        addMessage("assistant", chatData.error || "Gagal mendapatkan tanggapan RAG.", true);
      } else {
        addMessage("assistant", chatData.answer);
      }
    } else {
      loadingMsg.remove();
    }

  } catch (err) {
    loadingMsg.remove();
    addMessage("assistant", "Gagal menghubungi server. Pastikan server aplikasi (app.py) sedang berjalan.", true);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.classList.remove("uploading");
    sendBtn.disabled = false;
    input.focus();
  }
}

/**
 * Handler untuk Quick Suggestion Pills
 */
function sendQuickQuery(text) {
  if (!text) return;
  sendMessage(text);
}

/**
 * Fungsi untuk Menampilkan & Membatalkan Preview File
 */
function renderFilePreview(fileName) {
  filePreviewContainer.innerHTML = `
    <div class="preview-card" style="padding: 8px 12px; background: rgba(0,0,0,0.05); border-radius: 8px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
      <span>📄 <strong>${fileName}</strong> tersimpan (siap dikirim)</span>
      <button type="button" id="cancel-file-btn" style="background:none; border:none; color:red; cursor:pointer;">✖ Batal</button>
    </div>
  `;
  filePreviewContainer.style.display = 'block';

  document.getElementById('cancel-file-btn').addEventListener('click', cancelFileSelection);
}

function cancelFileSelection() {
  selectedFile = null;
  fileInput.value = '';
  filePreviewContainer.style.display = 'none';
  filePreviewContainer.innerHTML = '';
}

/* ==========================================================================
   Event Listeners & Initialization
   ========================================================================== */

// Event listener saat file dipilih
fileInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      addMessage("assistant", "Saat ini hanya file PDF yang didukung.", true);
      cancelFileSelection();
      return;
    }
    selectedFile = file;
    renderFilePreview(file.name);

    // Otomatis isi teks pertanyaan default jika kolom input masih kosong
    if (!input.value.trim()) {
      input.value = "Pada file ini bisakah anda memberikan rangkuman isi?";
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 150) + "px";
    }
  }
});

// Event listener submit form (Kirim Pesan / File)
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();

  if (!text && !selectedFile) return;

  if (selectedFile) {
    processUploadAndSend(selectedFile, text);
  } else {
    sendMessage(text);
  }
});

// Event listener tombol Enter (Shift + Enter untuk baris baru)
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.requestSubmit();
  }
});

// Auto-expand tinggi textarea secara dinamis
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 150) + "px";
});

// Tombol paperclip membuka dialog pilih file
uploadBtn.addEventListener("click", () => {
  fileInput.click();
});

// Cek status koneksi ke server
async function checkStatus() {
  try {
    const res = await fetch("/api/chat", { method: "OPTIONS" });
    if (res.ok || res.status === 405) {
      statusEl.className = "status online";
      statusText.textContent = "Server Aktif";
    } else {
      throw new Error();
    }
  } catch (e) {
    statusEl.className = "status offline";
    statusText.textContent = "Server Terputus";
  }
}

// Jalankan cek status awal
checkStatus();