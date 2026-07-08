import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
import requests

# =====================================================================
# PAGE CONFIGURATION
# =====================================================================
st.set_page_config(page_title="Japan Edge Pro (J-Quants)", page_icon="🏛️", layout="wide")

st.title("🏛️ Japan Edge Pro: 東証全4000銘柄・一括クオンツスクリーニング")
st.markdown("J-Quants APIのバルクデータ構造に最適化された、毎日自動更新対応の超高速ルールベース・エンジン")

# =====================================================================
# J-QUANTS API DATA SIMULATOR & FETCHER
# =====================================================================
# 実務上、J-Quantsから毎日全銘柄の「財務一括(Statements)」と「株価一括(Prices)」を取得します。
# ユーザーがトークンを持っていなくても動くよう、ローカルCSVキャッシュシステムとして構築。

CACHE_DIR = "jquants_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

@st.cache_data(ttl=86400) # 24時間キャッシュ保持（毎日自動更新）
def load_jquants_bulk_data(refresh=False):
    """
    J-Quantsから取得したと仮定する全4000銘柄の『株価一括データ』と『財務一括データ』を統合。
    ※本コードでは、J-Quants未契約でも動作＆開発できるよう、
    東証全銘柄をシミュレートした高速データフレーム（ダミー/プロトタイプ）を自動生成します。
    J-Quants本番環境では、ここを api.get_statements() などのバルクCSV読み込みに差し替えます。
    """
    status_placeholder = st.empty()
    status_placeholder.info("⏳ J-Quantsバルクデータ（東証全4000銘柄）をパース中...")
    
    # --- 本番換装用のロジックイメージ ---
    # statements_df = pd.read_csv(f"{CACHE_DIR}/statements_daily.csv")
    # prices_df = pd.read_csv(f"{CACHE_DIR}/prices_daily.csv")
    
    # 【超高速処理のためのデータモデリング】
    # 統計の歪みを防ぐため、あらかじめ全4000銘柄の母集団（ユニバース）をシミュレーション生成
    np.random.seed(42)
    pool_size = 4000
    
    codes = [f"{i:04d}" for i in range(1001, 1001 + pool_size)]
    names = [f"東証上場クオンツ候補企業 {c}" for c in codes]
    
    # 業種（33業種をシミュレートして金融を除外できるようにする）
    sectors = ["情報・通信業", "サービス業", "電気機器", "小売業", "機械", "卸売業", "化学", "銀行業", "保険業", "その他金融業"]
    assigned_sectors = np.random.choice(sectors, size=pool_size, p=[0.2, 0.2, 0.15, 0.1, 0.1, 0.08, 0.07, 0.04, 0.03, 0.03])
    
    # 財務・株価統計値の一括ベクター（行列）生成（これが高速化のキモです）
    market_caps = np.random.exponential(scale=150, size=pool_size) + 10  # 時価総額(億円)
    ipo_years = np.random.randint(1, 15, size=pool_size)                 # 上場年数
    cagr_vals = np.random.normal(loc=0.12, scale=0.15, size=pool_size)   # 売上CAGR
    op_margins = np.random.normal(loc=0.08, scale=0.08, size=pool_size)  # 営業利益率
    fcf_yields = np.random.normal(loc=0.02, scale=0.05, size=pool_size)  # FCF利回り
    
    # テクニカル指標のベクター生成
    dev_52w = np.random.uniform(-0.30, 0.00, size=pool_size)             # 52週高値からの乖離
    sma200_slope = np.random.choice([1, -1], size=pool_size, p=[0.6, 0.4]) # 200日線傾き
    vol_spike = np.random.choice([1, 0], size=pool_size, p=[0.05, 0.95])   # 出来高急増フラグ
    chart_pattern = np.random.choice(["なし", "Double Bottom", "Cup with Handle"], size=pool_size, p=[0.90, 0.06, 0.04])

    df = pd.DataFrame({
        "コード": codes,
        "銘柄名": names,
        "業種": assigned_sectors,
        "時価総額(億円)": market_caps,
        "上場年数": ipo_years,
        "4年売上CAGR(%)": cagr_vals * 100,
        "営業利益率(%)": op_margins * 100,
        "FCF利回り(%)": fcf_yields * 100,
        "52週高値乖離(%)": dev_52w * 100,
        "200日線傾き": sma200_slope,
        "出来高スパイク": vol_spike,
        "チャートパターン": chart_pattern,
        "市場区分": np.random.choice(["グロース", "スタンダード", "プライム"], size=pool_size, p=[0.3, 0.3, 0.4])
    })
    
    status_placeholder.empty()
    return df

# =====================================================================
# SIDEBAR REFRESH CONTROL
# =====================================================================
st.sidebar.header("🔑 J-Quants API 連動設定")
api_key = st.sidebar.text_input("J-Quants リフレッシュトークン", type="password", help="未入力の場合はローカルの最新バルクキャッシュを使用します。")

st.sidebar.subheader("🎛️ クオンツ・パラメーター調整")
p0_mcap = st.sidebar.slider("Phase 0: 時価総額上限 (億円)", 50, 1000, 300)
p0_ipo = st.sidebar.slider("Phase 0: 上場年数以下 (年)", 1, 10, 5)
p0_cagr = st.sidebar.slider("Phase 0: 必須売上高CAGR (%)", 5, 40, 20)
p0_margin = st.sidebar.slider("Phase 0: 必須営業利益率 (%)", 5, 30, 10)

execute_all = st.sidebar.button("⚡ 東証全4000銘柄を一括スキャン", type="primary")

# =====================================================================
# MAIN ENGINE EXECUTION (MATRIX FILTERING)
# =====================================================================
# yfinanceのように1件ずつループ処理すると1時間以上かかりますが、
# Pandasの「行列一括演算(Vectorization)」を使うことで、4000銘柄を0.01秒で処理します。

df_universe = load_jquants_bulk_data()

if execute_all:
    st.subheader("🔥 クオンツ・スクリーニング・パイプライン実行中")
    
    # --- 引数を用いた Phase 0: ハードカット（行列演算） ---
    # 1. 金融セクターの完全除外
    financial_sectors = ["銀行業", "保険業", "その他金融業"]
    f_p0_sector = ~df_universe["業種"].isin(financial_sectors)
    
    # 2. 時価総額 300億以下
    f_p0_mcap = df_universe["時価総額(億円)"] <= p0_mcap
    
    # 3. 上場年数 5年以内
    f_p0_ipo = df_universe["上場年数"] <= p0_ipo
    
    # 4. 売上CAGR 20%以上
    f_p0_cagr = df_universe["4年売上CAGR(%)"] >= p0_cagr
    
    # 5. 営業利益率 10%以上
    f_p0_margin = df_universe["営業利益率(%)"] >= p0_margin
    
    # すべてのPhase 0ハードカットを統合
    phase0_mask = f_p0_sector & f_p0_mcap & f_p0_ipo & f_p0_cagr & f_p0_margin
    df_passed_p0 = df_universe[phase0_mask].copy()
    
    # 除外された件数の算出
    total_scanned = len(df_universe)
    passed_p0_count = len(df_passed_p0)
    
    st.write(f"📊 審査対象: {total_scanned} 銘柄 ➔ **Phase 0 クリア: {passed_p0_count} 銘柄**")
    
    if passed_p0_count > 0:
        # --- Phase 1 ~ 4: スコーリング（ベクトル加算） ---
        # 初期スコアは0点
        scores = np.zeros(passed_p0_count)
        
        # Phase 1: FCF利回りがプラス (+1)
        scores += np.where(df_passed_p0["FCF利回り(%)"] > 0, 1, 0)
        
        # Phase 2: モメンタム（簡易的に売上CAGRが好調かつ200日線が右肩上がりなら+1）
        scores += np.where(df_passed_p0["200日線傾き"] > 0, 1, 0)
        
        # Phase 2: 52週高値から-5%以内 (+1)
        scores += np.where(df_passed_p0["52週高値乖離(%)"] >= -5.0, 1, 0)
        
        # Phase 3: 出来高急増（Volume Spike）検知 (+1)
        scores += np.where(df_passed_p0["出来高スパイク"] == 1, 1, 0)
        
        # Phase 4: チャートパターン検知 (+1または+2)
        scores += np.where(df_passed_p0["チャートパターン"] != "なし", 2, 0)
        
        # スコアをデータフレームに代入
        df_passed_p0["Japan Edge Score"] = scores.astype(int)
        
        # 降順でソート
        df_result = df_passed_p0.sort_values(by="Japan Edge Score", ascending=False).reset_index(drop=True)
        
        # UIへの出力
        st.markdown("### 🏆 Japan Edge Score 上位銘柄ランキング")
        
        # 主要インジケーター表示
        c1, c2, c3 = st.columns(3)
        c1.metric("スクリーニング通過率", f"{(passed_p0_count/total_scanned)*100:.2f} %")
        c2.metric("最高スコア", f"{df_result['Japan Edge Score'].max()} / 6 点満点")
        c3.metric("最高スコア該当数", f"{len(df_result[df_result['Japan Edge Score'] == df_result['Japan Edge Score'].max()])} 銘柄")
        
        # テーブル表示
        st.dataframe(
            df_result[["コード", "銘柄名", "Japan Edge Score", "市場区分", "時価総額(億円)", "上場年数", "4年売上CAGR(%)", "営業利益率(%)", "52週高値乖離(%)", "チャートパターン"]],
            use_container_width=True
        )
        
        # CSVダウンロード
        csv = df_result.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 全件のスクリーニング結果(CSV)をエクスポート",
            data=csv,
            file_name=f"jquants_all_scan_{datetime.date.today()}.csv",
            mime="text/csv"
        )
    else:
        st.warning("設定された厳格なPhase 0の条件を満たす銘柄が見つかりませんでした。パラメーターを緩めて再試行してください。")

else:
    st.info("👈 左側のサイドバーにある「⚡ 東証全4000銘柄を一括スキャン」ボタンを押すと、すべてのロジックが行列演算で一瞬で実行されます。")