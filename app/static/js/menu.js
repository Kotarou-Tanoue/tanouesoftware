(function () {
    const menuButton = document.getElementById("menuButton");
    const menu = document.getElementById("menu");
    const menuClose = document.getElementById("menuClose");
    if (!menuButton || !menu || !menuClose) return;

    menuButton.addEventListener("click", function () {
        menu.classList.add("active");
        menuButton.style.display = "none";
    });

    menuClose.addEventListener("click", function () {
        menu.classList.remove("active");
        menuButton.style.display = "flex";
    });
})();