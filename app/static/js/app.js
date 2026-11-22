/**
 * College Notice Board Management System - Core JavaScript
 */

// Toast notification helper
function showToast(message, type = "info") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
      <span style="font-size:0.9rem;font-weight:500;">${message}</span>
    </div>
    <button style="background:none;border:none;cursor:pointer;color:#94a3b8;font-size:1.1rem;" onclick="this.parentElement.remove()">×</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 4000);
}

// Password toggle helper
function initPasswordToggles() {
  document.querySelectorAll(".password-toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      const input = document.getElementById(targetId);
      if (input) {
        if (input.type === "password") {
          input.type = "text";
          btn.textContent = "Hide";
        } else {
          input.type = "password";
          btn.textContent = "Show";
        }
      }
    });
  });
}

// Confirmation modal helper
let currentConfirmCallback = null;

function showConfirmModal(title, message, confirmBtnText, onConfirm, isDanger = true) {
  const modal = document.getElementById("confirmModal");
  if (!modal) return;
  
  document.getElementById("confirmModalTitle").textContent = title;
  document.getElementById("confirmModalBody").textContent = message;
  const btn = document.getElementById("confirmModalActionBtn");
  btn.textContent = confirmBtnText;
  btn.className = isDanger ? "btn btn-danger" : "btn btn-primary";
  
  currentConfirmCallback = onConfirm;
  modal.classList.add("active");
}

function closeConfirmModal() {
  const modal = document.getElementById("confirmModal");
  if (modal) modal.classList.remove("active");
  currentConfirmCallback = null;
}

// Quick notice status updater
async function updateNoticeStatus(noticeId, newStatus) {
  try {
    const res = await fetch(`/api/faculty/notices/${noticeId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || `Status updated to ${newStatus}`, "success");
      setTimeout(() => window.location.reload(), 600);
    } else {
      showToast(data.detail || "Failed to update status", "error");
    }
  } catch (err) {
    showToast("Network error. Please try again.", "error");
  }
}

// Delete notice handler
function confirmDeleteNotice(noticeId, noticeTitle) {
  showConfirmModal(
    "Delete Notice",
    `Are you sure you want to permanently delete the notice "${noticeTitle}"? This will also remove any attachments and viewership logs.`,
    "Yes, Delete",
    async () => {
      try {
        const res = await fetch(`/api/faculty/notices/${noticeId}`, {
          method: "DELETE"
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.message || "Notice deleted successfully", "success");
          setTimeout(() => window.location.reload(), 600);
        } else {
          showToast(data.detail || "Failed to delete notice", "error");
        }
      } catch (err) {
        showToast("Network error. Please try again.", "error");
      }
    },
    true
  );
}

// Logout helper
async function handleLogout() {
  try {
    const res = await fetch("/api/auth/logout", { method: "POST" });
    if (res.ok) {
      window.location.href = "/login?success=You+have+been+logged+out.";
    } else {
      window.location.href = "/login";
    }
  } catch (err) {
    window.location.href = "/login";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initPasswordToggles();

  const confirmActionBtn = document.getElementById("confirmModalActionBtn");
  if (confirmActionBtn) {
    confirmActionBtn.addEventListener("click", () => {
      if (typeof currentConfirmCallback === "function") {
        currentConfirmCallback();
      }
      closeConfirmModal();
    });
  }

  const confirmCancelBtn = document.getElementById("confirmModalCancelBtn");
  if (confirmCancelBtn) {
    confirmCancelBtn.addEventListener("click", closeConfirmModal);
  }
});
