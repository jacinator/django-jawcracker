(function() {
    const saved = htmx.find("#toast-saved");
    const urls = { j: null, k: null };

    document.addEventListener("jawcracker:detail", ({ detail: { nextUrl, prevUrl } }) => {
        urls.j = nextUrl;
        urls.k = prevUrl;

        const detail = htmx.find("#detail");
        const active = htmx.find("#list .translation-item.active");

        active.scrollIntoView({ behavior: "smooth", block: "center" });
        detail.focus();
    });

    document.addEventListener("jawcracker:saved", () => {
        htmx.addClass(saved, "show");
        htmx.removeClass(saved, "show", 3000);
    });

    document.addEventListener("keydown", (event) => {
        const tag = document.activeElement?.tagName;
        const url = urls[event.key];

        if (
            tag !== "INPUT"
            && tag !== "TEXTAREA"
            && tag !== "SELECT"
            && typeof url !== "undefined"
            && url !== null
        ) {
            event.preventDefault();
            htmx.ajax("GET", url, { target: "#detail", swap: "outerHTML" });;
        }
    });
} ());
