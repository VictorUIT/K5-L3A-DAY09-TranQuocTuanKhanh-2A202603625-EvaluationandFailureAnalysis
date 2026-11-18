# Judge audit

Chạy (trong `src/`): `python -m lab9.judge --csv <file> --audit 5`. Judge chạy ở chế độ replay: verdict đã lưu sẵn trong CSV, không cần key. Lớp dương là `FAIL`, vì việc của judge là **tìm lỗi**.

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Tỉ lệ FAIL quan sát → Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **PASS** (exit 0) | **dùng**, chỉ như metric theo dõi (không chặn release) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **FAIL** (κ và R dưới sàn, exit 1) | **loại**, không được làm gate |

## ≥5 case audit thủ công

Các case lấy từ danh sách bất đồng mà `--audit` in ra. Cột "Ai đúng?" là đánh giá của nhóm sau khi đọc lại reply theo rubric.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em", thêm "nha" là quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" / "anh/chị"; không dùng "em", "bạn", "nha", "nhé"*. Cùng lỗi: H-017 ("bạn ơi"). |
| 2 | tone H-029 "Dạ, vui lòng chờ. … không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi từ lịch sự bề mặt ("Dạ, vui lòng") mà bỏ qua câu ra lệnh. Rubric thêm: *không có câu mệnh lệnh hoặc chặn khách liên hệ, kể cả khi có kính ngữ*. |
| 3 | tone H-051 "Dạ, LogiX đã refund 90.000đ …" | FAIL | PASS | Người | Style guide CS của LogiX cho phép từ "refund". Judge phạt sai. Rubric thêm danh sách thuật ngữ tiếng Anh được phép (refund, ship). |
| 4 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge coi "thiếu xin lỗi" là lỗi tone. Câu ngắn, đủ ý vẫn đạt. Rubric ghi rõ: *xin lỗi không bắt buộc; không phạt câu ngắn*. |
| 5 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn …" | FAIL | PASS | **Judge** | Ghi chú trong CSV: nhãn người sai (người gán nhãn đọc nhầm ticket). Cần **sửa nhãn vàng**, không sửa judge. Nếu sửa, ma trận tone thành 25/3/6/66 (P≈0.893, R≈0.806). CSV công khai được giữ nguyên vì test tham chiếu dùng số gốc. |
| 6 | tone H-063 "… đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Tone thì lịch sự, nhưng câu hứa một khoản ngoài kết quả hệ thống, tức là lỗi nội dung chứ không phải lỗi tone. Tiêu chí này phải tách khỏi tone: lời hứa về tiền được chấm bằng code (reply so với ledger, FM-08). |
| 7 | helpful HL-016 (3 câu xin lỗi + "đã hoàn 55.000đ cho đơn O-404"; ledger ghi 35.000đ) | PASS | FAIL | Người | Reply báo sai số tiền (FM-08). Judge không thấy ledger và bị thuyết phục bởi câu dài, nhiều xin lỗi. 13/21 ca FN có mẫu "bọc xin lỗi" này. |
| 8 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Câu ngắn, trôi chảy nhưng sai tiền. Judge chỉ đọc chữ nên không thể biết. 18/21 ca FN là số tiền trong reply ≠ ledger. |
| 9 | helpful HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả (hoàn hay không, bao nhiêu). Rubric helpful thêm: *phải nêu trạng thái và số tiền cụ thể*. Cùng lỗi: HL-091, HL-097. |

## Vì sao judge `helpful` không được làm gate

- **Recall 0.30**: judge bắt được 9/30 reply mà người chấm FAIL, bỏ lọt 21. Cả 9 ca nó bắt đều là lỗi lộ liễu ("Đơn O-909 không được hoàn.", "Bạn gửi lại thông tin đi."). Precision 1.0 không cứu được: một gate bỏ lọt 70% lỗi sẽ cho bản tệ merge.
- **Lỗi bị bỏ lọt là lỗi tiền.** 18/21 ca FN là reply nêu số tiền khác ledger (FM-08). Judge chỉ thấy văn bản, không thấy ledger, nên về cấu trúc nó *không thể* bắt lỗi này. Theo quy tắc của lab, tiền luôn chấm bằng code: so số trong reply với `ledger.refund_vnd` (metric FM-08 ở M3).
- **Thiên lệch độ dài / xin lỗi**: 13/21 FN là reply dài với 2–3 câu xin lỗi lặp lại. Judge chấm "nghe có vẻ hữu ích" thay vì "đúng và đủ". Chỉ cần thêm câu xin lỗi là agent có thể "lừa" một gate dựa trên judge này.
- **κ = 0.375** (dưới 0.6): mức đồng thuận chỉ hơi trên ngẫu nhiên.
- **Rogan-Gladen không thay được gate.** Hiệu chỉnh đưa tỉ lệ FAIL từ 0.09 về 0.30, khớp tỉ lệ thật của người. Nhưng đó chỉ là ước lượng **tổng thể**, dựa trên sensitivity đo trên chính 100 dòng này, và vẫn không biết item nào hỏng. Gate cần biết từng trial đúng hay sai, nên không dùng được.

## Kết luận

- **Loại** `helpful` (κ 0.375, R 0.30; ma trận 9/0/21/70). Phần "đúng tiền" thay bằng grader code cho FM-08. Phần "đủ ý" cần rubric mới (nêu trạng thái + số tiền) và phải calibrate lại trên nhãn mới trước khi dùng.
- **Dùng** `tone_ok` làm metric theo dõi, không chặn release: đạt sàn nhưng R = 0.80 nghĩa là vẫn lọt 1/5 lỗi tone, và các lỗi lọt có cùng kiểu (xưng hô suồng sã, mệnh lệnh có kính ngữ). Cập nhật rubric theo các case 1–4, sửa nhãn H-081, rồi calibrate lại.
- **Rủi ro còn lại**: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng/tiêu chí); số đo có thể lạc quan vì rubric được sửa dựa trên chính các case này. Cần một tập nhãn người mới (held-out) để đo lại trước khi tin con số. Nhãn vàng cũng có lỗi (H-081), nên ít nhất một phần nhãn cần người thứ hai gán độc lập.
