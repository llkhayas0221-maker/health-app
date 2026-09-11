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
    if os.path.exists('credentials.json'):
        credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    else:
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    
    gc = gspread.authorize(credentials)
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
        
        # --- 1. 基本データの入力部分 ---
        st.subheader("基本データ")
        record_date = st.date_input("日付", value=date.today())
        weight = st.number_input("朝の体重 (kg)", min_value=0.0, format="%.1f")
        
        # ご希望の順番：体重 -> 体脂肪率 -> 睡眠時間
        body_fat = st.number_input("体脂肪率 (%)", min_value=0.0, format="%.1f")
        sleep_time = st.text_input("睡眠時間 (例: 7h30m)")
        
        steps = st.number_input("歩数", min_value=0, step=100)

        # --- 2. 運動の入力部分 ---
        st.subheader("運動")
        exercise_options = ["なし", "筋トレ→傾斜", "傾斜ウォーキング", "ランニング", "その他"]
        exercise_selected = st.selectbox("本日の運動内容", exercise_options)

        if exercise_selected == "その他":
            exercise_other = st.text_input("具体的な運動内容を入力してください")
            exercise_content = exercise_other
        else:
            exercise_content = exercise_selected

        # --- 3. 食事・栄養データの入力（折りたたみ） ---
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

        # --- 保存ボタンを押したときの処理（自動ソート＆上書き対応） ---
        if submit_button:
            date_str = record_date.strftime("%Y/%m/%d")
            
            new_row_data = [
                date_str,
                str(weight) if weight > 0 else "",
                str(body_fat) if body_fat > 0 else "",
                str(protein) if protein > 0 else "",
                str(fat) if fat > 0 else "",
                str(carbs) if carbs > 0 else "",
                str(calories) if calories > 0 else "",
                str(steps) if steps > 0 else "",
                sleep_time,
                exercise_content,
                notes
            ]
            
            try:
                # 1. スプレッドシートの全データを取得
                all_values = worksheet.get_all_values()
                if not all_values:
                    header = ["日付", "朝の体重(kg)", "体脂肪率(%)", "タンパク質(g)", "脂質(g)", "炭水化物(g)", "消費カロリー(kcal)", "歩数", "睡眠時間", "運動内容", "備考"]
                    rows = []
                else:
                    header = all_values[0]
                    rows = all_values[1:]
                
                # 2. すでに同じ日付の行があれば上書き、なければ追加
                updated = False
                for i, row in enumerate(rows):
                    if row and row[0].replace('-', '/') == date_str.replace('-', '/'):
                        rows[i] = new_row_data
                        updated = True
                        break
                
                if not updated:
                    rows.append(new_row_data)
                
                # 3. 日付順（古い順）に綺麗にソート
                if rows:
                    df_temp = pd.DataFrame(rows)
                    df_temp['parsed_date'] = pd.to_datetime(df_temp[0], errors='coerce')
                    df_temp = df_temp.sort_values(by='parsed_date', ascending=True).drop(columns=['parsed_date'])
                    df_temp = df_temp.dropna(subset=[0])
                    sorted_rows = df_temp.values.tolist()
                else:
                    sorted_rows = []

                # 4. スプレッドシートを更新
                worksheet.clear()
                worksheet.append_row(header)
                if sorted_rows:
                    worksheet.append_rows(sorted_rows)
                    
                st.success(f"{date_str} のデータを保存し、日付順に整理しました！🎉")
                    
            except Exception as e:
                st.error(f"書き込みエラー: {e}")

with tab2:
    st.subheader("体重と体脂肪率の推移")
    
    st.sidebar.subheader("🎯 目標設定")
    target_weight = st.sidebar.number_input("目標体重 (kg)", value=60.0, step=0.1)
    target_fat = st.sidebar.number_input("目標体脂肪率 (%)", value=15.0, step=0.1)

    try:
        records = worksheet.get_all_records()
        if records:
            df = pd.DataFrame(records)
            
            df['朝の体重(kg)'] = pd.to_numeric(df.get('朝の体重(kg)', []), errors='coerce')
            df['体脂肪率(%)'] = pd.to_numeric(df.get('体脂肪率(%)', []), errors='coerce')
            
            df_clean = df.dropna(subset=['朝の体重(kg)', '体脂肪率(%)'])

            if not df_clean.empty:
                # --- 体重グラフ ＋ 目標ライン ---
                st.write("■ 朝の体重 (kg)")
                weight_line = alt.Chart(df_clean).mark_line(point=True).encode(
                    x=alt.X('日付', title='日付', sort=None),
                    y=alt.Y('朝の体重(kg)', scale=alt.Scale(zero=False), title='体重(kg)'),
                    tooltip=['日付', '朝の体重(kg)']
                )
                target_w_rule = alt.Chart(pd.DataFrame({'target': [target_weight]})).mark_rule(color='red', strokeDash=[5, 5]).encode(y='target')
                st.altair_chart(weight_line + target_w_rule, use_container_width=True)

                # --- 体脂肪率グラフ ＋ 目標ライン ---
                st.write("■ 体脂肪率 (%)")
                fat_line = alt.Chart(df_clean).mark_line(point=True, color='orange').encode(
                    x=alt.X('日付', title='日付', sort=None),
                    y=alt.Y('体脂肪率(%)', scale=alt.Scale(zero=False), title='体脂肪率(%)'),
                    tooltip=['日付', '体脂肪率(%)']
                )
                target_f_rule = alt.Chart(pd.DataFrame({'target': [target_fat]})).mark_rule(color='orange', strokeDash=[5, 5]).encode(y='target')
                st.altair_chart(fat_line + target_f_rule, use_container_width=True)
            else:
                st.info("有効な数値データがありません。")
        else:
            st.info("データがありません。記録を追加するとグラフが表示されます。")
    except Exception as e:
        st.warning(f"データの読み込みに失敗しました。詳細: {e}")