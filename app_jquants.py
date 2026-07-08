import base64
import gzip
import io
import re
import pandas as pd
import streamlit as st

# ==========================================
# 0. アプリケーションの基本設定
# ==========================================
st.set_page_config(
    page_title="JPX 銘柄スクリーナー",
    page_icon="📈",
    layout="wide",
)

# ==========================================
# 1. 埋め込みデータ（Base64文字列）
# ==========================================
# 💡 ここにお持ちの「実在4000銘柄の巨大な英数字データ」をそのまま貼り付けてください。
# トリミングや改行の心配は不要です。下の関数が自動でゴミを除去します。
COMPRESSED_DATA = """
H4sICAAAAAAA/2RmaXNoLmNzdgDTVchLzEsvUtJRSM7PyS8pSc1NzStJLVIoSk1M0S9KzEtPVgBKKgVl
pqXmFwGZJZn5CqWp6Zl5Chklmfl5CgWpJSVAtYlFmXkpQLU6CgWpOfmleSUgA0GWSgWpxSVA9QA1AyzS
WgAAAA==
"""


# ==========================================
# 2. 安全なデータ復元ロジック（エラー対策済）
# ==========================================
@st.cache_data
def load_embedded_tse_data():
    """埋め込まれたBase64データから東証銘柄マスターを安全に復元する"""

    # 【対策1】文字列型を保証し、前後の不要な空白をカット
    raw_str = str(COMPRESSED_DATA).strip()

    # 【対策2】Base64の正規文字（A-Z, a-z, 0-9, +, /, =）以外をすべて強制除外！
    # これにより、コピペ時に混入した全角スペースや目に見えない改行による ValueError を完全に防ぎます。
    clean_str = re.sub(r"[^A-Za-z0-9+/=]", "", raw_str)

    try:
        # クレンジング済みデータでデコードを実行
        compressed_bytes = base64.b64decode(clean_str)

        # Gzip解凍してPandas DataFrameに変換
        with gzip.GzipFile(fileobj=io.BytesIO(compressed_bytes)) as f:
            df = pd.read_csv(f)

        # 銘柄コードの書式を「4桁の文字列（例: 7203）」に統一
        if "Code" in df.columns:
            df["Code"] = df["Code"].astype(str).str.zfill(4)

        return df

    except Exception as e:
        st.error("⚠️ 埋め込みデータの復元（デコード・解凍）に失敗しました。")
        st.error(f"システムエラー詳細: {e}")
        # 後続のクラッシュを防ぐため、最低限の列を持つ空のDataFrameを返す
        return pd.DataFrame(columns=["Code", "Name", "Market", "Sector"])


# ==========================================
# 3. メインアプリケーション画面
# ==========================================
def main():
    st.title("📈 JPX 東証全市場 スクリーニングツール")
    st.caption("内蔵データ駆動型マスターデータ・スクリーナー")

    # データの読み込み
    df_universe = load_embedded_tse_data()

    if df_universe.empty:
        st.warning(
            "データが正常に読み込めなかったため、アプリケーションを停止しました。Base64データを確認してください。"
        )
        return

    # --- サイドバー: 検索・条件絞り込み ---
    st.sidebar.header("🔍 絞り込み条件")

    # キーワード検索
    search_query = st.sidebar.text_input(
        "銘柄名・コードで検索", placeholder="例: トヨタ、7203"
    )

    # 市場区分での絞り込み
    if "Market" in df_universe.columns:
        markets = ["すべて"] + sorted(df_universe["Market"].dropna().unique().tolist())
        selected_market = st.sidebar.selectbox("市場区分", markets)
    else:
        selected_market = "すべて"

    # 業種での絞り込み
    if "Sector" in df_universe.columns:
        sectors = ["すべて"] + sorted(df_universe["Sector"].dropna().unique().tolist())
        selected_sector = st.sidebar.selectbox("33業種区分", sectors)
    else:
        selected_sector = "すべて"

    # --- データのフィルタリング処理 ---
    df_filtered = df_universe.copy()

    if search_query:
        df_filtered = df_filtered[
            df_filtered["Code"].str.contains(search_query, case=False, na=False)
            | df_filtered["Name"].str.contains(search_query, case=False, na=False)
        ]

    if selected_market != "すべて":
        df_filtered = df_filtered[df_filtered["Market"] == selected_market]

    if selected_sector != "すべて":
        df_filtered = df_filtered[df_filtered["Sector"] == selected_sector]

    # --- メインダッシュボード表示 ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("総銘柄数", f"{len(df_universe)} 銘柄")
    with col2:
        st.metric("該当銘柄数", f"{len(df_filtered)} 銘柄")
    with col3:
        st.metric("データデコード", "正常（クレンジング済）")

    st.write("---")

    # 結果表示
    st.subheader("📋 銘柄一覧")
    st.dataframe(
        df_filtered,
        column_config={
            "Code": st.column_config.TextColumn("銘柄コード"),
            "Name": st.column_config.TextColumn("会社名"),
            "Market": st.column_config.TextColumn("市場"),
            "Sector": st.column_config.TextColumn("業種"),
        },
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()