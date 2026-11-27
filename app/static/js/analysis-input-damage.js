        // ----- 写真のドラッグ＆ドロップ -----
        const dropArea = document.getElementById("drop-area");
        const photoInput = document.getElementById("photos");
        const fileList = document.getElementById("file-list");

        // 選ばれたファイル名を表示する
        function showFileNames() {
            const names = Array.from(photoInput.files).map(function (file) {
                return file.name;
            });
            fileList.textContent = names.join("、");
        }

        photoInput.addEventListener("change", showFileNames);

        ["dragenter", "dragover"].forEach(function (eventName) {
            dropArea.addEventListener(eventName, function (e) {
                e.preventDefault();
                dropArea.style.backgroundColor = "#eaf3ff";
            });
        });

        ["dragleave", "drop"].forEach(function (eventName) {
            dropArea.addEventListener(eventName, function (e) {
                e.preventDefault();
                dropArea.style.backgroundColor = "";
            });
        });

        dropArea.addEventListener("drop", function (e) {
            if (e.dataTransfer.files.length > 0) {
                photoInput.files = e.dataTransfer.files;
                showFileNames();
            }
        });


        // ----- 「その他」を選んだときだけ、自由入力欄を表示する -----
        const OTHER_VALUE = {{ other_value|tojson }};

        [
            ["location-name", "location-name-other-wrap"],
            ["location-type", "location-type-other-wrap"],
            ["damage-type", "damage-type-other-wrap"]
        ].forEach(function (pair) {

            const select = document.getElementById(pair[0]);
            const wrap = document.getElementById(pair[1]);

            function toggleOther() {
                wrap.style.display = (select.value === OTHER_VALUE) ? "block" : "none";
            }

            select.addEventListener("change", toggleOther);

            // 初期状態(入力エラーで再表示されたときも、選択に合わせて表示する)
            toggleOther();

        });