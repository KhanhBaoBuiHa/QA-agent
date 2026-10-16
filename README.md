# ShopQA-Agent

Agent AI tự **sinh, chạy và kiểm tra test E2E** cho website thương mại điện tử từ một file mô tả tính năng.
Xây bằng **LangGraph + Playwright + LLM (Gemini)**, có shop demo với lỗi cài sẵn để đo xem agent bắt được lỗi hay không.

> **Trạng thái:** MVP chạy được từ đầu đến cuối (sinh test, chạy bằng trình duyệt thật, báo lỗi kèm ảnh chụp).
> Phần phân loại bằng LLM, tự sửa test và Langfuse vẫn đang làm, xem mục [Trạng thái và kế hoạch](#trạng-thái-và-kế-hoạch).
> Mã nguồn nằm trong thư mục `shopqa-agent/`.

## Ý tưởng

Một bạn QA đọc yêu cầu, tự viết danh sách việc cần kiểm tra, bấm thử trên website rồi ghi lại cái nào hỏng.
ShopQA-Agent làm đúng quy trình đó:

1. Đọc **file spec** mô tả tính năng (vd `specs/checkout.md`).
2. Mở trang thật, **liệt kê các phần tử UI** đang có (nút, ô nhập, `data-testid`).
3. LLM sinh các **test case** dưới dạng JSON, chỉ được dùng phần tử có thật.
4. Playwright **chạy từng bước** trong trình duyệt sạch, chụp ảnh từng bước.
5. Báo test nào pass, test nào fail, kèm bước hỏng, loại lỗi và ảnh.

## Kiến trúc

![Luồng chạy của agent](shopqa-agent/docs/agent_kiem_thu_luong_chay.png)

*Sơ đồ đích. Các node `classify`, `repair_test` và Langfuse chưa hoàn thiện, xem bảng bên dưới.*

| Node | Việc làm | Trạng thái |
|---|---|---|
| `generate_tests` | LLM sinh test dạng JSON, kiểm tra schema bằng pydantic, tự thử lại tối đa 3 lần nếu JSON sai | Xong |
| `run_tests` | Playwright chạy từng bước, mỗi test một trình duyệt sạch, chụp ảnh từng bước | Xong |
| `classify` | Phân loại pass / lỗi thật / lỗi do test | Tạm: quy tắc theo loại lỗi (`assertion_failed` được coi là lỗi thật), chưa dùng LLM |
| `repair_test` | Tự sửa test bị lỗi do viết sai, chạy lại tối đa 3 lần | Chưa làm (chỉ đếm lượt) |
| `report` | Tổng hợp kết quả | Tạm: danh sách đơn giản |

`graph.py` dựng hai phiên bản để so sánh: **A** (không tự sửa) và **B** (có vòng tự sửa).

### Các quyết định thiết kế

- **Test là danh sách action có cấu trúc, không phải code LLM viết.** Các action gồm `goto`, `click`, `fill`, `select`,
  `expect_text`, `expect_visible`, `expect_enabled`, `expect_disabled`, `expect_url`... Nhờ vậy không phải `exec()` code lạ,
  mỗi bước log được riêng, và việc sửa test chỉ là sửa vài dòng JSON.
- **LLM "nghĩ", code cố định "chạy".** Phần chạy test không dùng LLM nên agent không thể tự nhận là pass,
  kết quả lặp lại được và đo được.
- **Chống bịa selector.** Trước khi sinh test, agent mở trang thật và đưa cho LLM danh sách phần tử UI làm nguồn duy nhất được dùng.
- **Phân biệt loại lỗi.** Mỗi test fail có `error_type`: `assertion_failed` (có phần tử nhưng nội dung sai, tín hiệu mạnh của lỗi thật),
  `element_not_found` (selector sai hoặc web thiếu phần tử), `navigation_error`, `invalid_action`...
- **Shop demo có lỗi cài sẵn**, bật bằng tham số trên địa chỉ: `?bug=coupon`, `?bug=checkout`.

## Kết quả đo

Thiết lập: model `gemini-3.8-flash`, nhiệt độ 0, shop `mini_shop`, spec `specs/checkout.md`.
Số liệu hiện còn ít, đọc như dữ liệu ban đầu chứ chưa phải kết luận thống kê.

| Chế độ | Prompt | Số lần chạy | Kết quả |
|---|---|---|---|
| `bug=coupon` (giảm 1% thay vì 10%) | ban đầu | 1 | **Bỏ sót lỗi**: test chỉ kiểm tra thông báo "Áp dụng thành công", tổng 99.000đ vẫn PASS |
| `bug=coupon` | thêm quy tắc "phải tự tính và kiểm tra con số kỳ vọng" | 7 | **Bắt được 7/7**, đều `assertion_failed` |
| `bug=checkout` | sau khi sửa | chưa đo | |
| Shop sạch (không có lỗi) | ban đầu | 1 | 6/6 PASS, 0 báo nhầm |
| Shop sạch | sau khi sửa | chưa đo | |

Ví dụ báo cáo của một lần chạy `bug=coupon`:

```
[FAIL] t3: Áp dụng mã giảm giá SALE10 thành công
- t3: real_bug phần tử có nhưng kết quả khác kỳ vọng
    ✗ 6. expect_text [data-testid="cart-total"] = 'Tổng: 90.000đ' -> assertion_failed:
      kỳ vọng chứa 'Tổng: 90.000đ', thực tế là 'tổng: 99.000đ'
```

**Bài học rút ra:** lần chạy đầu agent bỏ sót lỗi không phải vì phần chạy test sai, mà vì LLM sinh test chưa đủ chặt.
Thêm hai quy tắc vào prompt (kiểm tra con số tính được, mỗi điểm của spec cần ít nhất một test kiểm tra kết quả của chính nó)
đã khắc phục trong các lần chạy sau. Bảng số liệu chi tiết nằm ở `shopqa-agent/docs/shopqa-ket-qua-do.xlsx`.

## Chạy thử

Yêu cầu: Python 3.10 trở lên và một khóa API của nhà cung cấp LLM (mặc định dùng Gemini).

```bash
cd shopqa-agent
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Tạo file `.env` (sao chép từ `.env.example`) và điền:

```
LLM_PROVIDER=google
LLM_MODEL=<tên model Gemini>
GOOGLE_API_KEY=<khóa của bạn>
```

Dùng nhà cung cấp khác thì cài thêm gói tương ứng (`langchain-anthropic`, `langchain-openai`, `langchain-ollama`)
và đổi `LLM_PROVIDER` (`anthropic`, `openai`, `ollama`).

**Cửa sổ 1: bật shop demo**

```bash
cd demo_shop/mini_shop
python -m http.server 8000
```

**Cửa sổ 2: chạy agent**

```powershell
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m shopqa.cli --spec specs/checkout.md --base-url "http://localhost:8000"
```

```bash
# macOS / Linux
export PYTHONPATH=src
python -m shopqa.cli --spec specs/checkout.md --base-url "http://localhost:8000"
```

Bật lỗi cài sẵn bằng cách thêm tham số vào địa chỉ:

```
--base-url "http://localhost:8000/?bug=coupon"      # giảm giá sai
--base-url "http://localhost:8000/?bug=checkout"    # nút thanh toán không bị vô hiệu khi giỏ trống
```

Dùng `--no-self-repair` để chạy phiên bản A. Ảnh chụp từng bước và `run.json` được lưu trong `artifacts/<thời gian>/`.

**Chạy kiểm thử của chính project** (cần Chromium; không cần khóa API):

```bash
pytest
```

## Cấu hình (`.env`)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `LLM_PROVIDER` | `google`, `anthropic`, `openai`, `ollama` | `anthropic` |
| `LLM_MODEL` | tên model của nhà cung cấp (bắt buộc) | |
| `SHOPQA_LLM_TIMEOUT` | số giây chờ tối đa cho mỗi lần gọi LLM | `60` |
| `SHOPQA_LLM_RETRIES` | số lần tự thử lại khi lỗi tạm thời (quá tải, hết hạn mức) | `2` |
| `SHOPQA_MAX_TESTS` | số test tối đa mỗi lần sinh | `6` |
| `SHOPQA_TIMEOUT_MS` | thời gian chờ tối đa cho mỗi bước trình duyệt | `5000` |
| `SHOPQA_HEADLESS` | `0` để xem trình duyệt chạy thật | `1` |
| `SHOPQA_ARTIFACTS` | thư mục lưu ảnh và kết quả | `artifacts` |

## Cấu trúc thư mục

```
shopqa-agent/
├── src/shopqa/
│   ├── graph.py          # dựng đồ thị LangGraph (phiên bản A/B)
│   ├── state.py          # state chạy qua các node
│   ├── schemas.py        # kiểm tra JSON do LLM sinh ra
│   ├── llm.py            # chọn nhà cung cấp LLM theo .env
│   ├── cli.py, log.py    # chạy từ dòng lệnh, in tiến độ
│   ├── nodes/            # generate_tests, run_tests, stubs (classify, repair_test, report)
│   ├── prompts/          # prompt tách riêng khỏi code
│   └── tools/browser.py  # hàm bọc Playwright, đọc phần tử UI
├── demo_shop/mini_shop/  # shop demo một trang, có lỗi cài sẵn
├── specs/checkout.md     # mô tả tính năng làm đầu vào cho agent
├── tests/                # 14 test pytest (LLM giả + trình duyệt thật)
└── docs/                 # sơ đồ và bảng số liệu
```

## Hạn chế hiện tại

- **Số liệu còn ít** và chỉ dùng một model; LLM sinh bộ test khác nhau mỗi lần nên kết quả có thể dao động.
- **Shop demo nhỏ** (một trang, hai lỗi cài sẵn), chưa phản ánh website thật.
- **`classify` mới là quy tắc đơn giản**, chưa phân tích được các trường hợp mơ hồ (ví dụ phần tử không tìm thấy có thể do selector sai hoặc do web thiếu phần tử).
- Chưa chạy trên các sàn thương mại điện tử thật (có thể vi phạm điều khoản sử dụng); chỉ dùng shop demo.

## Trạng thái và kế hoạch

- [x] Sinh test bằng LLM, kiểm tra schema, thử lại khi sai
- [x] Chạy test bằng Playwright, chụp ảnh, phân loại loại lỗi
- [x] Shop demo với lỗi cài sẵn và bộ kiểm thử tự động (14 test)
- [x] Đo ban đầu cho `bug=coupon`
- [ ] Đo `bug=checkout` và shop sạch với prompt đã sửa (tỉ lệ báo nhầm)
- [ ] `classify` dùng LLM, đọc log và ảnh chụp
- [ ] `repair_test` tự sửa test viết sai rồi chạy lại
- [ ] Tích hợp Langfuse để xem trace từng bước
- [ ] Bộ lỗi cài sẵn lớn hơn (15-20 lỗi) và script đo so sánh phiên bản A/B

## Công nghệ

Python, LangGraph, LangChain, Playwright, pydantic, pytest, Gemini API.
