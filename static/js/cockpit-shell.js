(function () {
    const shell = document.getElementById("cockpitShell");
    const toggle = document.getElementById("sidebarToggle");
    const backdrop = document.getElementById("sidebarBackdrop");
    if (!shell || !toggle) {
        return;
    }

    function setOpen(open) {
        shell.classList.toggle("sidebar-open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (backdrop) {
            backdrop.setAttribute("aria-hidden", open ? "false" : "true");
        }
    }

    toggle.addEventListener("click", function () {
        setOpen(!shell.classList.contains("sidebar-open"));
    });

    if (backdrop) {
        backdrop.addEventListener("click", function () {
            setOpen(false);
        });
    }

    shell.querySelectorAll(".sidebar a, .sidebar button, .sidebar select").forEach(function (el) {
        el.addEventListener("click", function () {
            if (el.classList.contains("nav-section-toggle")) {
                return;
            }
            if (window.matchMedia("(max-width: 768px)").matches) {
                setOpen(false);
            }
        });
    });
})();
