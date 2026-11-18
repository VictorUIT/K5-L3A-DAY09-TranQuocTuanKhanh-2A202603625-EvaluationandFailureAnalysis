# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case của nhóm: `seeded_regression` C-008@11

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11
python -m lab9.trace_case --shape fixed --claim C-008 --seed 11   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-008@11`, item E-008, run ID `E-seeded_regression-20261117-90bf` (`src/reports/eval_seeded_regression.json`) |
| Triệu chứng | Grader Lab 8 **PASS** (`ok`), `refund_amount_correct` PASS, nhưng `reply_matches_ledger` **FAIL**. Ledger ghi **20.000đ** (đúng nhãn: approval A-008 chỉ duyệt 20.000 < quote 35.000), còn reply nói với khách **"Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."** |
| Bước sai đầu tiên | Event **5** `reply` `{"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}` |
| Vì sao là bước *đầu tiên* | Event 2 `investigator` đọc đúng O-808 (trễ 4 ngày, phí 35.000). Event 3 `quote` 35.000 đúng `SHIP-LATE-03`. Event 4 `refund_history` 0 đúng: đơn chưa hoàn lần nào, nên bước tự trừ của `pre_deducted` không đổi số và không sinh event `proposal`. Host ghi ledger 20.000 theo trần approval, đúng luật "refund = min(quote, approved, paid)". Sai đầu tiên là lúc soạn reply: agent báo số **nó tự tính** (proposal 35.000) thay vì số host đã ghi (`effect.amount_vnd` 20.000). |
| Failure mode | **FM-08** misreport (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed` C-008@11: event 1–3 giống hệt, không có `refund_history`, event 4 `reply` "đã hoàn **20.000đ**"; ledger 20.000. Khác biệt duy nhất là số trong reply lấy từ ledger hay từ proposal. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_c008_misreport_slips_past_lab8_but_not_reply_matches_ledger` (Lab 8 PASS, ledger 20.000, `ReplyMatchesLedger` FAIL với lý do nêu 35000 và 20000) và `test_c008_fixed_reply_quotes_the_ledger` (`fixed` PASS). Đã chạy: cả hai pass, tức grader **fail trên variant lỗi** và **pass trên `fixed`**. Ở mức eval set: metric `reply_matches_ledger` (chặn release) trên `seeded_regression` = 0.7857, Δ −0.214 so với baseline. |
| Chưa chắc chắn | Trace không ghi kết quả `issue_refund` (không có event cho số host đã commit), nên "host ghi 20.000" được đọc từ ledger, không từ trace. Trong `variant_agent`, công tắc gây ra hành vi này là `pre_deducted` (reply báo proposal), không phải `misreport`; hai công tắc cho cùng triệu chứng FM-08, trace không phân biệt được nguyên nhân. Grader dựa trên regex số tiền (`35.000đ`, `90,000 VND`); reply viết số bằng chữ ("ba mươi lăm nghìn") sẽ lọt. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
