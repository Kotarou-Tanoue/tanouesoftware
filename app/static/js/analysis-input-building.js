        const registeredBuilding = document.getElementById("registered-building");  // 未ログイン時はnull
        const newBuildingSection = document.getElementById("new-building-section");
        const submitExisting = document.getElementById("submit-existing");           // 未ログイン時はnull
        const submitNew = document.getElementById("submit-new");


        // 「新しい建物を入力する」(値 "0")が選ばれているかで、表示するフォームとボタンを切り替える
        function toggleBuildingForm() {

            const isNew = !registeredBuilding || registeredBuilding.value === "0";

            // 新しい建物の入力欄
            newBuildingSection.style.display = isNew ? "block" : "none";

            // ボタン(新規 → 新規用のボタン、登録済み → 登録済み用のボタン)
            submitNew.style.display = isNew ? "" : "none";

            if (submitExisting) {
                submitExisting.style.display = isNew ? "none" : "";
            }

        }


        if (registeredBuilding) {
            registeredBuilding.addEventListener("change", toggleBuildingForm);
        }


        // 初期状態
        toggleBuildingForm();