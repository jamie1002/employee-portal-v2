# Design：主管可檢視所屬部門的出勤明細

## Decision 1：範圍限縮放在 service，router 只掛角色 dependency

`GET /api/attendance` 的 router 只掛 `require_roles("admin", "manager")`，「這個人看得到誰」
由 service 判斷。

**為何不選另一個方案**：把部門限縮寫在 router（例如在 router 內讀 `current_user["role"]`
再決定要不要覆寫 `department_id`）看起來更短，但違反本專案的分層紀律——router 不做業務判斷。
更實際的理由是**同一份權限語意會被複製到第二個地方**：`attendance_changes` 已經在 service
層做了完全相同的判斷，若出勤明細改在 router 做，往後任何一次規則調整（例如未來允許主管
跨部門代管）都必須記得改兩個不同層的程式碼，漏改一處不會報錯，只會安靜地讓某一條路徑
放行過多資料。

**不這樣做會壞在哪**：router 層的限縮繞不過 service 直接被其他呼叫端重用。批 B 的 AI 工具
層要呼叫的是 service 函式，不是 HTTP 端點；如果限縮只存在於 router，AI 工具就會拿到一個
**完全沒有範圍限縮**的 `get_all()`，主管一問就看到全公司。

## Decision 2：抽出 `attendance_scope.resolve_visible_user_ids()`，出勤明細與出勤異動共用

`attendance_changes.get_changes()` 目前已有一段完整的「依角色解析可見 user_ids」邏輯
（admin 不限、manager 限自己部門且指定他部門成員回 403、其餘角色一律只看自己）。本變更把
這段抽成 `app/services/attendance_scope.py`，兩邊共用。

**為何不選另一個方案**：在 `attendance.get_all()` 裡照抄一份是最快的做法，但那正是
`docs/PITFALLS.md` C1 記錄過的失敗模式——權限判斷出現第二套實作。兩份實作在寫下的當下
一定是一致的，分歧發生在半年後只改了其中一份的時候。

**不這樣做會壞在哪**：具體的分歧情境是「未指派部門的 manager」。現行
`attendance_changes` 對這種帳號**拋 403**，理由寫在原始碼註解裡：沒有可限縮的範圍時
不得因此變成看全公司。若照抄時漏掉這個分支，`department_id = None` 會被
`user_repository.find_all(pool, department_id=None)` 解讀成「不篩選部門」，於是一個沒有
部門的主管會拿到**全公司**的出勤明細。這是 deny-by-default 寫反成 allow-by-default 的
教科書案例，而且不會報錯。

## Decision 3：不動 `export._scope_filters()`

匯出的範圍限縮語意與本變更一致（非 admin 強制自己部門、指定他部門成員回 403），但**作用
單位不同**：`_scope_filters()` 處理的是五種匯出 kind 的 `filters` 字典，還帶著
`room-bookings` 不限縮的例外；本變更處理的是「可見的 user_ids 清單」。

**為何不選另一個方案**：把兩者合併成單一權限函式在原則上更漂亮，但那要求同時重構匯出的
五種 kind 與 `room-bookings` 例外，改動面積遠大於本變更本身，而匯出目前有完整的綠燈測試
保護。把一個明確的 bug 修正擴張成跨模組重構，是拿已經驗證過的東西去換一個沒有立即收益的
形狀。列為後續項目，不在本變更範圍。

## Decision 4：主管的部門篩選鎖死，不是隱藏

主管進入該頁時，部門篩選呈現為**唯讀標籤**顯示自己的部門名稱，而不是直接移除該欄位。

**為何不選另一個方案**：直接隱藏會讓主管誤以為自己看到的是全公司資料，畫面上沒有任何線索
說明資料被限縮過。保留一個唯讀標籤，主管一眼就知道「我看的是研發部」。**前端這個處理純粹
是 UX，不是安全邊界**——即使使用者改前端狀態送出別的 `department_id`，後端仍然會覆蓋或
回 403。

## Decision 5：路由路徑維持 `/admin/attendance`

主管能進入一個路徑帶 `admin` 的頁面，觀感上不理想，但本變更不改名。

**為何不選另一個方案**：改名要同步改路由、選單、`docs/UI-SPEC.md` 路由表、e2e 的導頁斷言，
而收益純粹是觀感。URL 從來不是這個專案的權限邊界（每支端點自己掛 dependency），把一個
bug 修正跟一次路徑重新命名綁在一起，會讓這個 commit 在 review 時難以判斷哪些改動是必要的。

## Decision 6：頁面標題與選單文案依角色切換

admin 看到「全公司出勤」，manager 看到「部門出勤」。

**為何不選另一個方案**：統一叫「出勤查詢」可以不必分支，但對 admin 而言失去了「這裡是全
公司範圍」的重要資訊，對 manager 而言「全公司出勤」則是**錯誤描述**——他看到的根本不是
全公司。文案在這裡不是裝飾，它是使用者判斷「我現在看到的資料涵蓋多少人」的唯一線索。
