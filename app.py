import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import pandas as pd
import altair as alt
import os

# --- ページ設定とテーマ ---
st.set_page_config(page_title="健康管理アプリ", page_icon="💪", layout="centered")
st.title("健康管理ダッシュボード")

# --- スプレッドシートの連携設定 ---
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    # まずPC内に「credentials.json」があるか確認する
    if os.path.exists('credentials.json'):
        credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    else:
        # なければクラウド(Secrets)から読み込む
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    
    gc = gspread.authorize(credentials)
    
    # ↓ ここはご自身のスプレッドシートIDのままにしてください
    sh = gc.open_by_key("19JEpQqXD8cb2hpVEMOtnnYUjxLVvpHPdnLoHCNOf_MY") 
    worksheet = sh.sheet1
except Exception as e:
    st.error(f"接続エラー\n{e}")
    st.stop()

# --- タブの作成 ---
tab1, tab2 = st.tabs(["📝 記録する", "📈 データを見る"])

with tab1:
    st.write("今日のデータを入力してください")
    with st.form(key='record_form', clear_on_submit=True):
        
        # スマホで見やすいように1列表示を基本にする
        st.subheader("基本データ")
        input_date = st.date_input("日付", date.today())
        
        col1, col2 = st.columns(2)
        with col1:
            weight = st.number_input("朝の体重 (kg)", min_value=0.0, format="%.1f", step=0.1)
            sleep_input = st.text_input("睡眠時間 (例: 7h30m)")
        with col2:
            body_fat = st.number_input("体脂肪率 (%)", min_value=0.0, format="%.1f", step=0.1)
            steps = st.number_input("歩数", min_value=0, step=100)

        # 運動内容はドロップダウンで選択
        st.subheader("運動")
        exercise_options = ["オフ", "筋トレ→傾斜", "傾斜ウォーキング", "その他"]
        exercise_choice = st.selectbox("本日の運動内容", exercise_options)
        
        # 「その他」を選んだ時だけテキスト入力を表示
        if exercise_choice == "その他":
            exercise = st.text_input("具体的な運動内容を入力")
        else:
            exercise = exercise_choice

        # 食事データは「折りたたみ」にして画面をスッキリさせる
        with st.expander("食事・栄養データを入力"):
            st.write("※必要な場合のみ入力")
            col_pfc1, col_pfc2 = st.columns(2)
            with col_pfc1:
                protein = st.number_input("タンパク質 (g)", min_value=0.0, format="%.1f")
                fat = st.number_input("脂質 (g)", min_value=0.0, format="%.1f")
            with col_pfc2:
                carbs = st.number_input("炭水化物 (g)", min_value=0.0, format="%.1f")
                calories = st.number_input("消費カロリー (kcal)", min_value=0, step=10)

        notes = st.text_area("備考")
        submit_button = st.form_submit_button(label='シートに記録する')

        if submit_button:
            row_data = [
                input_date.strftime("%Y/%m/%d"),
                weight if weight > 0 else "",
                body_fat if body_fat > 0 else "",
                protein if protein > 0 else "",
                fat if fat > 0 else "",
                carbs if carbs > 0 else "",
                calories if calories > 0 else "",
                steps if steps > 0 else "",
                sleep_input, # テキストのまま保存
                exercise,
                notes
            ]
            try:
                worksheet.append_row(row_data)
                st.success("スプレッドシートに記録しました！🎉")
            except Exception as e:
                st.error(f"書き込みエラー: {e}")

with tab2:
    st.subheader("体重と体脂肪率の推移")
    try:
        # スプレッドシートの全データを取得
        records = worksheet.get_all_records()
        if records:
            df = pd.DataFrame(records)
            
            # グラフ化のために数値を整理
            df['朝の体重(kg)'] = pd.to_numeric(df.get('朝の体重(kg)', []), errors='coerce')
            df['体脂肪率(%)'] = pd.to_numeric(df.get('体脂肪率(%)', []), errors='coerce')
            
            # 空のデータを除外
            df_clean = df.dropna(subset=['朝の体重(kg)', '体脂肪率(%)'])

            # --- 体重グラフ (AltairでY軸を自動調整) ---
            st.write("■ 朝の体重 (kg)")
            weight_chart = alt.Chart(df_clean).mark_line(point=True).encode(
                x=alt.X('日付', title='日付'),
                y=alt.Y('朝の体重(kg)', scale=alt.Scale(zero=False), title='体重(kg)'), # zero=Falseで0始まりを解除
                tooltip=['日付', '朝の体重(kg)'] # マウスを重ねた時に数値を表示
            )
            st.altair_chart(weight_chart, use_container_width=True)

            # --- 体脂肪率グラフ ---
            st.write("■ 体脂肪率 (%)")
            fat_chart = alt.Chart(df_clean).mark_line(point=True, color='orange').encode(
                x=alt.X('日付', title='日付'),
                y=alt.Y('体脂肪率(%)', scale=alt.Scale(zero=False), title='体脂肪率(%)'),
                tooltip=['日付', '体脂肪率(%)']
            )
            st.altair_chart(fat_chart, use_container_width=True)
        else:
            st.info("データがありません。記録を追加するとグラフが表示されます。")
    except Exception as e:
        st.warning(f"データの読み込みに失敗しました。詳細: {e}")