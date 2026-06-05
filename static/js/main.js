const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.querySelector(".nav-links");
const toast = document.querySelector(".toast");

if (navToggle && navLinks) {
    navToggle.addEventListener("click", () => {
        const isOpen = navLinks.classList.toggle("is-open");
        navToggle.setAttribute("aria-expanded", String(isOpen));
    });
}

function showToast(message) {
    if (!toast) {
        return;
    }

    toast.textContent = message;
    toast.classList.add("is-visible");
    window.setTimeout(() => {
        toast.classList.remove("is-visible");
    }, 2400);
}

document.querySelectorAll(".status-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = form.querySelector(".status-button");
        const panel = form.closest(".status-actions");
        if (!button || !panel) {
            form.submit();
            return;
        }

        button.disabled = true;

        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: new FormData(form),
            });

            if (!response.ok) {
                throw new Error("Request failed");
            }

            const data = await response.json();
            panel.querySelectorAll(".status-button").forEach((item) => {
                item.classList.toggle("is-active", item.dataset.status === data.status);
            });
            panel.dataset.currentStatus = data.status;
            showToast(data.message);
        } catch (error) {
            form.submit();
        } finally {
            button.disabled = false;
        }
    });
});
