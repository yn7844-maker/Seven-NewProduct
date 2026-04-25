# Seven-NewProduct

신상품 과거 Raw Data 대시보드 프로젝트입니다.

`dashboard_app.py`를 기준으로 신상품의 예약주문, 초도발주량, 매출 기준 실수요를 제품별/센터별로 조회할 수 있고, 과거 raw data와 예약/수요 비교 화면도 함께 확인할 수 있습니다.

## 실행 방법

```bash
cd "/Users/elena/Documents/New project"
python3 -m pip install -r requirements.txt
python3 -m streamlit run dashboard_app.py
```

## 필요 파일

아래 파일들이 `dashboard_app.py`와 같은 폴더에 있어야 합니다.

| 파일 | 설명 |
|---|---|
| `dashboard_app.py` | 메인 Streamlit 대시보드 |
| `requirements.txt` | 실행 패키지 목록 |
| `final_preorder.csv` | 신상품 예약주문/초도발주/분류 정보 |
| `A1_final_center_order.csv` | 센터별 발주/출고 데이터 |
| `A4_final_CENTER_STK.csv` | 센터 재고 데이터 |
| `center_sales_final.csv` | 센터별 매출/실수요 데이터 |

## 주요 탭

### 제품 별 데이터

- 대분류 `과자` 기준으로 중분류, 소분류, 센터를 선택할 수 있습니다.
- 제품별 또는 센터별로 아래 지표를 한눈에 볼 수 있습니다.
  - 예약주문 수
  - 초도발주량
  - 실수요

### 예약/수요 비교

- 과거 신상품을 검색해서 제품별 요약 데이터를 확인할 수 있습니다.
- 선택한 상품에 대해 신상품 정보와 센터별 예약주문, 초도발주량, 실수요량을 비교할 수 있습니다.

### 과거 Raw Data

- 원본 CSV 기준으로 필터를 적용해 raw data를 조회할 수 있습니다.

### 과거 신상품 조회

- 과거 상품명을 검색해 유사 사례를 빠르게 찾을 수 있습니다.

### 카테고리 비교

- 중분류/소분류 기준으로 예약주문량, 초도발주량, 실수요를 비교할 수 있습니다.

### 기준월 신상품

- 기준일 직전 31일 안에 출시된 신상품 목록을 볼 수 있습니다.

## 설치 패키지

현재 `requirements.txt` 기준 패키지는 아래와 같습니다.

- `pandas`
- `plotly`
- `streamlit`
