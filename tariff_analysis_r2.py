import streamlit as st
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

# 페이지 설정
st.set_page_config(
    page_title="우회수입 세율분석 챗봇",
    page_icon="📊",
    layout="wide"
)

# 제목
st.title("📊 우회수입 세율차 TOP10 자동 분석")
st.markdown("---")

# 데이터 로드 함수
@st.cache_data
def load_json_data(filepath):
    """JSON 파일 로드"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 데이터가 리스트인지 확인
        if isinstance(data, list):
            return data
        # 딕셔너리인 경우
        elif isinstance(data, dict):
            # tariff_rates.json: "아시아지역만" 키
            if "아시아지역만" in data and isinstance(data["아시아지역만"], list):
                return data["아시아지역만"]
            # import_volume.json: "수출입 실적(품목별+국가별)" 키
            elif "수출입 실적(품목별+국가별)" in data and isinstance(data["수출입 실적(품목별+국가별)"], list):
                return data["수출입 실적(품목별+국가별)"]
            # 일반적인 키들 확인
            for key in ['data', 'items', 'records', 'rows']:
                if key in data and isinstance(data[key], list):
                    return data[key]
            # 첫 번째 값이 리스트인 경우
            for value in data.values():
                if isinstance(value, list):
                    return value
            st.error(f"JSON 파일 구조를 인식할 수 없습니다: {filepath}")
            st.json(list(data.keys()))
            return None
        else:
            st.error(f"예상치 못한 JSON 형식입니다: {filepath}")
            return None
            
    except FileNotFoundError:
        st.error(f"파일을 찾을 수 없습니다: {filepath}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"JSON 형식이 올바르지 않습니다: {filepath}\n오류: {str(e)}")
        return None
    except Exception as e:
        st.error(f"파일 로드 중 오류 발생: {filepath}\n오류: {str(e)}")
        return None

# FTA 협정 매핑 (국가별) - RCEP 제외
FTA_MAPPING = {
    '중국': ['중국'],
    '베트남': ['베트남', 'ASEAN'],
    '태국': ['태국', 'ASEAN'],
    '인도네시아': ['인도네시아', 'ASEAN'],
    '말레이시아': ['말레이시아', 'ASEAN'],
    '싱가포르': ['싱가포르', 'ASEAN'],
    '필리핀': ['필리핀', 'ASEAN'],
    '미얀마': ['미얀마', 'ASEAN'],
    '캄보디아': ['캄보디아', 'ASEAN'],
    '라오스': ['라오스', 'ASEAN'],
    '브루나이': ['브루나이', 'ASEAN'],
    '일본': ['일본'],
    '호주': ['호주'],
    '뉴질랜드': ['뉴질랜드'],
    '인도': ['인도'],
    '미국': ['미국'],
    '칠레': ['칠레'],
    '터키': ['터키'],
    '페루': ['페루'],
    '콜롬비아': ['콜롬비아'],
}

def get_hs6_from_hs10(hs10):
    """HS10에서 HS6 추출"""
    return str(hs10)[:6]

def get_min_fta_rate(tariff_data, hs10, country, is_mfn=False):
    """특정 국가의 최소 FTA 세율 찾기 - 모든 가능한 협정 비교"""
    rates = []
    
    for item in tariff_data:
        item_hs10 = str(item.get('품목번호 10단위', '')).strip()
        
        if item_hs10 != str(hs10):
            continue
        
        agreement = item.get('협정명', '').strip()
        rate_str = str(item.get('관세율', '0')).strip()
        
        # 세율 파싱
        try:
            # '%' 제거하고 숫자만 추출
            rate_str = rate_str.replace('%', '').strip()
            if rate_str == '' or rate_str == 'null':
                rate = 0.0
            else:
                rate = float(rate_str)
            
            # MFN 세율
            if is_mfn and agreement == '기본세율':
                rates.append(rate)
            
            # FTA 세율 - ASEAN 국가는 모든 가능한 협정 확인
            elif not is_mfn and country in FTA_MAPPING:
                for fta in FTA_MAPPING[country]:
                    if fta in agreement:
                        rates.append(rate)
                        # break 제거 - 모든 협정을 확인해야 함
        except Exception as e:
            continue
    
    return min(rates) if rates else None

def calculate_tariff_difference(tariff_data, origin_country, transit_country):
    """세율차 계산 - FTA 세율 원본 표시"""
    results = []
    hs10_set = set()
    
    # HS10 목록 수집
    for item in tariff_data:
        hs10 = str(item.get('품목번호 10단위', '')).strip()
        if hs10 and len(hs10) == 10:
            hs10_set.add(hs10)
    
    st.info(f"📊 분석 대상 HS10 품목 수: {len(hs10_set)}개")
    
    processed = 0
    found_diff = 0
    
    # 각 HS10에 대해 세율 계산
    progress_bar = st.progress(0)
    for idx, hs10 in enumerate(hs10_set):
        progress_bar.progress((idx + 1) / len(hs10_set))
        
        hs6 = get_hs6_from_hs10(hs10)
        
        # 품명 찾기
        product_name = ""
        for item in tariff_data:
            if str(item.get('품목번호 10단위', '')).strip() == hs10:
                product_name = item.get('품명', '').strip()
                break
        
        if not product_name:
            continue
        
        # MFN 세율
        mfn_rate = get_min_fta_rate(tariff_data, hs10, None, is_mfn=True)
        if mfn_rate is None:
            continue
        
        processed += 1
        
        # 원산지국 FTA 세율 (모든 가능한 협정 중 최소값)
        origin_fta_raw = get_min_fta_rate(tariff_data, hs10, origin_country)
        
        # 경유국 FTA 세율 (모든 가능한 협정 중 최소값)
        transit_fta_raw = get_min_fta_rate(tariff_data, hs10, transit_country)
        
        # 표시용: FTA 세율 원본 그대로 표시
        origin_fta_display = origin_fta_raw if origin_fta_raw is not None else mfn_rate
        transit_fta_display = transit_fta_raw if transit_fta_raw is not None else mfn_rate
        
        # 계산용: 실제 적용 세율 = min(MFN, FTA)
        if origin_fta_raw is not None:
            direct_rate = min(mfn_rate, origin_fta_raw)
        else:
            direct_rate = mfn_rate
        
        if transit_fta_raw is not None:
            indirect_rate = min(mfn_rate, transit_fta_raw)
        else:
            indirect_rate = mfn_rate
        
        # 세율차 계산
        rate_diff = direct_rate - indirect_rate
        
        if rate_diff != 0:
            found_diff += 1
        
        # 세율차가 0보다 큰 경우만 포함
        if rate_diff > 0:
            results.append({
                'HS10': hs10,
                'HS6': hs6,
                '품명': product_name,
                'MFN': mfn_rate,
                '원산지국_FTA': origin_fta_display,
                '경유국_FTA': transit_fta_display,
                '직수출세율': direct_rate,
                '우회세율': indirect_rate,
                '세율차': rate_diff,
                '절감률': (rate_diff / direct_rate * 100) if direct_rate > 0 else 0
            })
    
    progress_bar.empty()
    
    st.info(f"""
    📈 분석 결과:
    - 전체 HS10 품목: {len(hs10_set)}개
    - MFN 세율 확인된 품목: {processed}개
    - 세율차 발견된 품목 (0 제외): {found_diff}개
    - 우회수입 리스크 품목 (세율차 > 0): {len(results)}개
    """)
    
    return results

def get_import_trend(import_data, hs6, transit_country):
    """수입 추세 분석 (HS6 기준)"""
    years_data = {2022: 0, 2023: 0, 2024: 0}
    
    # HS6를 6자리로 정규화
    hs6_normalized = str(hs6).strip()[:6]
    
    for item in import_data:
        item_hs6 = str(item.get('품목번호 6단위', '')).strip()[:6]
        item_country = item.get('수출국', '').strip()
        item_year_str = str(item.get('연도', '')).strip()
        
        # 연도 변환
        try:
            item_year = int(item_year_str)
        except:
            continue
        
        if item_hs6 == hs6_normalized and item_country == transit_country:
            try:
                amount_str = str(item.get('수입 금액(천 달러)', '0')).strip()
                amount = float(amount_str)
                if item_year in years_data:
                    years_data[item_year] += amount
            except:
                continue
    
    # 추이 판정 및 위험도 점수 계산
    if years_data[2024] > years_data[2022]:
        trend = "증가"
        risk = "🔴 높음"
        risk_score = 3
    elif years_data[2024] < years_data[2022]:
        trend = "감소"
        risk = "🟢 낮음"
        risk_score = 1
    else:
        trend = "유지"
        risk = "🟡 보통"
        risk_score = 2
    
    return {
        '2022': years_data[2022],
        '2023': years_data[2023],
        '2024': years_data[2024],
        '추이': trend,
        '위험도': risk,
        'risk_score': risk_score
    }

# 사이드바 입력
st.sidebar.header("🔍 분석 조건 입력")

# 파일 경로 설정
tariff_file = st.sidebar.text_input(
    "관세율 데이터 파일 경로",
    value="tariff_rates.json",
    help="tariff_rates.json 파일명 (같은 폴더에 있어야 함)"
)

import_file = st.sidebar.text_input(
    "수입통계 데이터 파일 경로",
    value="import_volume.json",
    help="import_volume.json 파일명 (같은 폴더에 있어야 함)"
)

# 국가 입력 - 기본값 공란으로 수정
origin_country = st.sidebar.text_input(
    "원산지국 (실제 생산국)",
    value="",
    placeholder="예: 중국, 베트남, 일본 등",
    help="예: 중국, 베트남, 일본 등"
)

transit_country = st.sidebar.text_input(
    "경유국 (원산지 둔갑 우려국)",
    value="",
    placeholder="예: 베트남, 태국 등",
    help="우회 경유 가능성이 의심되는 국가"
)

# 분석 실행 버튼
if st.sidebar.button("📊 분석 시작", type="primary"):
    
    # 국가명 입력 검증
    if not origin_country or not transit_country:
        st.error("⚠️ 원산지국과 경유국을 모두 입력해주세요!")
        st.stop()
    
    # 데이터 로드
    with st.spinner("데이터 로딩 중..."):
        tariff_data = load_json_data(tariff_file)
        import_data = load_json_data(import_file)
    
    if tariff_data and import_data:
        st.success("✅ 데이터 로드 완료!")
        
        # 데이터 미리보기 (디버깅용)
        with st.expander("📊 데이터 미리보기 (문제 해결용)"):
            st.write("**관세율 데이터 샘플:**")
            if isinstance(tariff_data, list) and len(tariff_data) > 0:
                st.json(tariff_data[0])
                st.write(f"총 {len(tariff_data)}개 항목")
            else:
                st.warning("관세율 데이터가 리스트 형태가 아닙니다.")
                
            st.write("**수입통계 데이터 샘플:**")
            if isinstance(import_data, list) and len(import_data) > 0:
                st.json(import_data[0])
                st.write(f"총 {len(import_data)}개 항목")
            else:
                st.warning("수입통계 데이터가 리스트 형태가 아닙니다.")
        
        # 핵심 요약
        st.header("📊 정리 완료했습니다!")
        st.subheader("핵심 요약")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("원산지국", origin_country)
        with col2:
            st.metric("경유국", transit_country)
        with col3:
            st.metric("분석 기준", "2025년 세율 / 2022-2024 수입통계")
        
        st.markdown("---")
        
        # 세율차 계산
        with st.spinner("세율차 분석 중..."):
            results = calculate_tariff_difference(tariff_data, origin_country, transit_country)
        
        if results:
            # TOP10 선정 (세율차 → 원산지국 세율 기준 정렬)
            df_results = pd.DataFrame(results)
            df_results = df_results.sort_values(
                by=['세율차', '원산지국_FTA', 'MFN'],
                ascending=[False, False, False]
            ).head(10)
            
            # 표1: TOP10 세율차 랭킹
            st.subheader("📋 표1: TOP10 세율차 랭킹 (HS10 기준)")
            
            display_df = df_results.copy()
            display_df.insert(0, '순위', range(1, len(display_df) + 1))
            display_df['세율차'] = display_df['세율차'].round(2)
            display_df['절감률'] = display_df['절감률'].round(2).astype(str) + '%'
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            
            # 표2: 수입 추세 (우회위험도 높은 순으로 정렬)
            st.subheader("📈 표2: 수입 추세 (HS6 기준) - 우회위험도 높은 순")
            
            trend_data = []
            
            # 표1의 모든 품목(HS10)을 HS6로 변환하여 표시 (중복 제거 없이)
            for _, row in df_results.iterrows():
                hs6 = row['HS6']
                product_name = row['품명']
                
                trend_info = get_import_trend(import_data, hs6, transit_country)
                
                trend_data.append({
                    'HS6': hs6,
                    '대표 품명': product_name[:30] + '...' if len(product_name) > 30 else product_name,
                    '2022금액(천$)': f"{trend_info['2022']:.1f}",
                    '2023금액(천$)': f"{trend_info['2023']:.1f}",
                    '2024금액(천$)': f"{trend_info['2024']:.1f}",
                    "추이('22→'24)": trend_info['추이'],
                    '우회위험도': trend_info['위험도'],
                    'risk_score': trend_info['risk_score']
                })
            
            df_trend = pd.DataFrame(trend_data)
            # 우회위험도 높은 순으로 정렬
            df_trend = df_trend.sort_values(by='risk_score', ascending=False)
            # risk_score 컬럼 제거
            df_trend = df_trend.drop(columns=['risk_score'])
            
            st.dataframe(
                df_trend,
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            
            # 결론 블록
            st.subheader("⚠️ 결론")
            
            high_risk_items = []
            for _, row in df_results.iterrows():
                hs6 = row['HS6']
                trend_info = get_import_trend(import_data, hs6, transit_country)
                
                if row['세율차'] > 0 and trend_info['추이'] == '증가':
                    high_risk_items.append(f"**{row['HS10']}** ({row['품명'][:20]}...)")
            
            if high_risk_items:
                st.error("**🔴 우회수입 고위험 품목**")
                for item in high_risk_items:
                    st.markdown(f"- {item}")
            else:
                st.success("**🟢 현재 우회수입 위험도 낮음**")
            
            st.warning("""
            **⚠️ 주의사항**
            - PSR(충분가공기준) 검토 필요
            - 상호대응 여부 미확인 시 추가 검증 필요
            - 본 분석은 참고용이며, 최종 신고 전 관세청 고시·FTA포털 원문 확인 권고
            """)
            
            st.markdown("---")
            st.caption("""
            **📌 각주**
            - 단위: 수량=톤, 금액=천달러
            - 데이터 기준: 2025년 관세율, 2022-2024년 수입통계
            - ASEAN 국가는 한-ASEAN 협정과 개별 FTA 협정 중 최소 세율 적용
            - FTA 세율은 모든 가능한 협정 중 최소값으로 표시되며, 실제 적용세율은 min(MFN, FTA)로 계산됨
            - 표2는 우회위험도(수입 증가 추세) 기준으로 정렬됨
            """)
            
        else:
            st.warning("세율차가 있는 품목이 발견되지 않았습니다.")
    
else:
    # 초기 화면
    st.info("""
    ### 👋 환영합니다!
    
    이 챗봇은 **우회수입 세율차 분석**을 자동으로 수행합니다.
    
    **사용 방법:**
    1. 왼쪽 사이드바에서 데이터 파일 경로 확인/수정
    2. 원산지국과 경유국 입력
    3. '📊 분석 시작' 버튼 클릭
    
    **필요한 파일:**
    - `tariff_rates.json`: 2025년 기준 관세율 데이터
    - `import_volume.json`: 2022-2024년 수입통계 데이터
    
    **분석 내용:**
    - TOP10 세율차 랭킹 (HS10 기준)
    - 수입 추세 분석 (HS6 기준, 우회위험도 높은 순)
    - 우회수입 위험도 평가
    
    **📌 ASEAN 국가 분석 시:**
    - 한-ASEAN 협정과 개별 FTA 협정 중 최소 세율이 자동으로 적용됩니다
    """)
    
    st.markdown("---")
    st.markdown("**📘 v3.1 (2025.10) | Powered by Streamlit | ASEAN 다중협정 지원**")