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

document.querySelectorAll(".remove-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = form.querySelector(".remove-button");
        if (!button) {
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
            showToast(data.message);
            
            // Remove the game card wrapper from the view
            const wrapper = form.closest(".game-card-wrapper");
            if (wrapper) {
                wrapper.style.opacity = "0";
                wrapper.style.transform = "scale(0.95)";
                setTimeout(() => {
                    wrapper.remove();
                    // Reload page to update counters
                    location.reload();
                }, 300);
            }
        } catch (error) {
            form.submit();
        } finally {
            button.disabled = false;
        }
    });
});

document.querySelectorAll(".favorite-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = form.querySelector(".heart-button");
        if (!button) {
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
            const label = button.querySelector(".heart-label");
            button.classList.toggle("is-favorited", data.is_favorited);
            if (label && data.label) {
                label.textContent = data.label;
                button.title = data.label;
            }
            showToast(data.message);
        } catch (error) {
            form.submit();
        } finally {
            button.disabled = false;
        }
    });
});
