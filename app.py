import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import pandas as pd
import altair as alt
import os
import numpy as np

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

# --- 目標値の読み込み（Z1セル・AA1セル） ---
try:
    saved_w_val = worksheet.cell(1, 26).value  # Z列(26)
    saved_f_val = worksheet.cell(1, 27).value  # AA列(27)
    
    default_target_w = float(saved_w_val) if saved_w_val and str(saved_w_val).strip() != "" else 60.0
    default_target_f = float(saved_f_val) if saved_f_val and str(saved_f_val).strip() != "" else 15.0
except Exception:
    default_target_w = 60.0
    default_target_f = 15.0

if 'saved_target_weight' not in st.session_state:
    st.session_state.saved_target_weight = default_target_w
if 'saved_target_fat' not in st.session_state:
    st.session_state.saved_target_fat = default_target_f

# --- ヘッダーの基本設定（A列〜N列） ※順番を変更しました ---
HEADER_DEFAULT = ["日付", "朝の体重(kg)", "体脂肪率(%)", "タンパク質(g)", "脂質(g)", "炭水化物(g)", "消費カロリー(kcal)", "歩数", "睡眠時間", "運動内容", "総消費カロリー(kcal)", "摂取カロリー(kcal)", "カロリーマイナス(kcal)", "備考"]

# --- カロリー計算関数 ---
def calc_calories_for_sheet(w_str, f_str, p_str, lipid_str, c_str, active_cals_str):
    try:
        w = float(w_str) if w_str else 0.0
        f = float(f_str) if f_str else 0.0
        p = float(p_str) if p_str else 0.0
        lipid = float(lipid_str) if lipid_str else 0.0
        c = float(c_str) if c_str else 0.0
        active_cals = float(active_cals_str) if active_cals_str else 0.0
        
        # 基礎代謝 (ステータス: 166.5cm, 20歳, 男性)
        if w > 0:
            mifflin = 10 * w + 6.25 * 166.5 - 5 * 20 + 5
            if f > 0:
                lbm = w * (1 - f / 100)
                katch = 370 + 21.6 * lbm
                bmr = (mifflin + katch) / 2
            else:
                bmr = mifflin
        else:
            bmr = 0.0
            
        total_burn = bmr + active_cals
        intake = p * 4 + lipid * 9 + c * 4
        
        out_burn = f"{total_burn:.0f}" if total_burn > 0 else ""
        out_intake = f"{intake:.0f}" if intake > 0 else ""
        out_minus = f"{(total_burn - intake):.0f}" if (intake > 0 and total_burn > 0) else ""
        
        return out_burn, out_intake, out_minus
    except:
        return "", "", ""

# --- タブの作成 ---
tab1, tab2 = st.tabs(["📝 記録する", "📈 データを見る"])

with tab1:
    st.write("今日のデータを入力してください")
    with st.form(key='record_form', clear_on_submit=True):
        
        st.subheader("基本データ")
        record_date = st.date_input("日付", value=date.today())
        weight = st.number_input("朝の体重 (kg)", min_value=0.0, format="%.1f", step=0.1, value=None)
        
        body_fat = st.number_input("体脂肪率 (%)", min_value=0.0, format="%.1f", step=0.1, value=None)
        sleep_time = st.text_input("睡眠時間 (例: 7h30m)", value="")
        steps = st.number_input("歩数", min_value=0, step=100, value=None)

        st.subheader("運動")
        exercise_options = ["なし", "筋トレ→傾斜", "傾斜ウォーキング", "ランニング", "その他"]
        exercise_selected = st.selectbox("本日の運動内容", exercise_options)
        exercise_content = exercise_selected

        with st.expander("食事・栄養データを入力"):
            st.write("※必要な場合のみ入力")
            col_pfc1, col_pfc2 = st.columns(2)
            with col_pfc1:
                protein = st.number_input("タンパク質 (g)", min_value=0.0, format="%.1f", step=0.1, value=None)
                fat_input = st.number_input("脂質 (g)", min_value=0.0, format="%.1f", step=0.1, value=None)
            with col_pfc2:
                carbs = st.number_input("炭水化物 (g)", min_value=0.0, format="%.1f", step=0.1, value=None)
                calories = st.number_input("消費カロリー (kcal)", min_value=0, step=10, value=None)

        notes = st.text_area("備考", value="")
        submit_button = st.form_submit_button(label='シートに記録する')

        if submit_button:
            date_str = record_date.strftime("%Y/%m/%d")
            
            try:
                # 範囲をA〜N列に限定して取得
                all_values = worksheet.get('A:N')
                
                if not all_values:
                    header = HEADER_DEFAULT.copy()
                    rows = []
                else:
                    header = all_values[0]
                    while len(header) < 14:
                        header.append(HEADER_DEFAULT[len(header)])
                    # ヘッダーも新しい並びに強制修正
                    header = HEADER_DEFAULT.copy()
                    rows = all_values[1:]
                
                existing_row = None
                target_index = -1
                for i, row in enumerate(rows):
                    if row and row[0].replace('-', '/') == date_str.replace('-', '/'):
                        existing_row = row
                        target_index = i
                        break
                
                if existing_row:
                    while len(existing_row) < 14:
                        existing_row.append("")
                    
                    m_weight = str(weight) if weight is not None else existing_row[1]
                    m_fat = str(body_fat) if body_fat is not None else existing_row[2]
                    m_protein = str(protein) if protein is not None else existing_row[3]
                    m_lipid = str(fat_input) if fat_input is not None else existing_row[4]
                    m_carbs = str(carbs) if carbs is not None else existing_row[5]
                    m_cals = str(calories) if calories is not None else existing_row[6]
                    m_steps = str(steps) if steps is not None else existing_row[7]
                    m_sleep = sleep_time if sleep_time.strip() != "" else existing_row[8]
                    m_exercise = exercise_content if exercise_content != "なし" else (existing_row[9] if existing_row[9] else "なし")
                    
                    # 備考の位置が変更されたので existing_row[13] を参照
                    m_notes = notes if notes.strip() != "" else existing_row[13]
                    
                    out_burn, out_intake, out_minus = calc_calories_for_sheet(m_weight, m_fat, m_protein, m_lipid, m_carbs, m_cals)
                    
                    merged_row = [
                        date_str, m_weight, m_fat, m_protein, m_lipid, 
                        m_carbs, m_cals, m_steps, m_sleep, m_exercise,
                        out_burn, out_intake, out_minus, m_notes
                    ]
                    rows[target_index] = merged_row
                else:
                    m_weight = str(weight) if weight is not None else ""
                    m_fat = str(body_fat) if body_fat is not None else ""
                    m_protein = str(protein) if protein is not None else ""
                    m_lipid = str(fat_input) if fat_input is not None else ""
                    m_carbs = str(carbs) if carbs is not None else ""
                    m_cals = str(calories) if calories is not None else ""
                    m_steps = str(steps) if steps is not None else ""
                    
                    out_burn, out_intake, out_minus = calc_calories_for_sheet(m_weight, m_fat, m_protein, m_lipid, m_carbs, m_cals)
                    
                    new_row = [
                        date_str, m_weight, m_fat, m_protein, m_lipid, 
                        m_carbs, m_cals, m_steps, sleep_time, exercise_content,
                        out_burn, out_intake, out_minus, notes
                    ]
                    rows.append(new_row)
                
                if rows:
                    df_temp = pd.DataFrame(rows)
                    df_temp['parsed_date'] = pd.to_datetime(df_temp[0], errors='coerce')
                    df_temp = df_temp.sort_values(by='parsed_date', ascending=True).drop(columns=['parsed_date'])
                    
                    df_temp = df_temp.fillna("").astype(str)
                    df_temp = df_temp.dropna(subset=[0])
                    sorted_rows = df_temp.values.tolist()
                else:
                    sorted_rows = []

                if len(all_values) > 1 and len(sorted_rows) == 0:
                    st.error("安全装置が作動しました：データ損失を防ぐため書き込みを中断しました。")
                else:
                    data_to_write = [header] + sorted_rows
                    worksheet.batch_clear(["A:N"])
                    try:
                        worksheet.update(range_name="A1", values=data_to_write)
                    except TypeError:
                        worksheet.update("A1", data_to_write)
                        
                    st.success(f"{date_str} のデータを統合・保存しました！🎉")
                    
            except Exception as e:
                st.error(f"書き込みエラー（データは保護されています）: {e}")

with tab2:
    st.subheader("体重と体脂肪率の推移")
    
    # --- データ読み込み（A〜N列のみ） ---
    df = pd.DataFrame()
    try:
        data = worksheet.get('A:N')
        if data and len(data) > 1:
            header = HEADER_DEFAULT.copy()
            valid_rows = []
            for r in data[1:]:
                padded = r + [""] * (14 - len(r))
                valid_rows.append(padded[:14])
            df = pd.DataFrame(valid_rows, columns=header)
    except Exception as e:
        st.warning(f"データの読み込みに失敗しました。詳細: {e}")
    
    # --- ストリーク（連続記録）の計算 ---
    streak = 0
    if not df.empty:
        try:
            valid_dates = pd.to_datetime(df['日付'], errors='coerce').dropna().dt.date.unique()
            valid_dates = sorted(valid_dates, reverse=True)
            check_date = date.today()
            if check_date not in valid_dates:
                check_date = date.today() - timedelta(days=1)
            while check_date in valid_dates:
                streak += 1
                check_date -= timedelta(days=1)
        except Exception:
            pass

    # --- サイドバー：目標設定 ---
    st.sidebar.subheader("🎯 目標設定")
    temp_target_weight = st.sidebar.number_input("目標体重 (kg)", value=st.session_state.saved_target_weight, step=0.1)
    temp_target_fat = st.sidebar.number_input("目標体脂肪率 (%)", value=st.session_state.saved_target_fat, step=0.1)

    if st.sidebar.button("変更を保存する"):
        st.session_state.saved_target_weight = temp_target_weight
        st.session_state.saved_target_fat = temp_target_fat
        try:
            worksheet.update_cell(1, 26, temp_target_weight)
            worksheet.update_cell(1, 27, temp_target_fat)
            st.sidebar.success("目標をスプレッドシートに保存しました！✨")
        except Exception as e:
            st.sidebar.error(f"保存エラー: {e}")
            
    if streak > 0:
        st.sidebar.markdown(f"<div style='text-align: left; color: #888; font-size: 0.9em; margin-top: 10px;'>🔥 {streak}日間 記録継続中</div>", unsafe_allow_html=True)

    current_target_w = st.session_state.saved_target_weight
    current_target_f = st.session_state.saved_target_fat

    if not df.empty:
        df['朝の体重(kg)'] = pd.to_numeric(df.get('朝の体重(kg)', []), errors='coerce')
        df['体脂肪率(%)'] = pd.to_numeric(df.get('体脂肪率(%)', []), errors='coerce')
        
        df_clean = df.dropna(subset=['朝の体重(kg)', '体脂肪率(%)'])

        if not df_clean.empty:
            latest_row = df_clean.iloc[-1]
            latest_weight = latest_row['朝の体重(kg)']
            latest_fat = latest_row['体脂肪率(%)']

            if latest_weight <= current_target_w and latest_fat <= current_target_f:
                st.balloons()
                st.success(f"🎉 おめでとうございます！目標（体重: {current_target_w}kg / 体脂肪率: {current_target_f}%）を達成しました！新しい目標を設定しよう。")

            with st.expander("🔮 目標達成予測を見る (直近トレンド分析)"):
                if len(df_clean) >= 5:
                    df_recent = df_clean.tail(14).copy()
                    df_recent['parsed_date'] = pd.to_datetime(df_recent['日付'], errors='coerce')
                    df_recent = df_recent.dropna(subset=['parsed_date']).sort_values('parsed_date')
                    
                    if len(df_recent) >= 2:
                        start_date = df_recent['parsed_date'].iloc[0]
                        end_date = df_recent['parsed_date'].iloc[-1]
                        total_days = (end_date - start_date).days
                        
                        if total_days > 0:
                            start_w = df_recent['朝の体重(kg)'].iloc[0]
                            end_w = df_recent['朝の体重(kg)'].iloc[-1]
                            daily_w_change = (end_w - start_w) / total_days
                            
                            start_f = df_recent['体脂肪率(%)'].iloc[0]
                            end_f = df_recent['体脂肪率(%)'].iloc[-1]
                            daily_f_change = (end_f - start_f) / total_days
                            
                            col_p1, col_p2 = st.columns(2)
                            
                            with col_p1:
                                st.markdown("##### ⚖️ 体重の予測")
                                if current_target_w >= latest_weight:
                                    st.success("✨ すでに目標体重に到達しています！")
                                elif daily_w_change >= 0:
                                    st.info("📈 トレンドが横ばいか増加傾向のため算出できません。")
                                else:
                                    diff_w = latest_weight - current_target_w
                                    days_to_target_w = int(diff_w / abs(daily_w_change))
                                    target_date_w = date.today() + timedelta(days=days_to_target_w)
                                    st.metric(label="目標体重まで", value=f"約 {days_to_target_w} 日", delta=f"予定日: {target_date_w.strftime('%Y/%m/%d')}")
                            
                            with col_p2:
                                st.markdown("##### 📉 体脂肪率の予測")
                                if current_target_f >= latest_fat:
                                    st.success("✨ すでに目標体脂肪率に到達しています！")
                                elif daily_f_change >= 0:
                                    st.info("📈 トレンドが横ばいか増加傾向のため算出できません。")
                                else:
                                    diff_f = latest_fat - current_target_f
                                    days_to_target_f = int(diff_f / abs(daily_f_change))
                                    target_date_f = date.today() + timedelta(days=days_to_target_f)
                                    st.metric(label="目標体脂肪率まで", value=f"約 {days_to_target_f} 日", delta=f"予定日: {target_date_f.strftime('%Y/%m/%d')}")
                        else:
                            st.info("予測を計算するための日付間隔が不足しています。")
                    else:
                        st.info("直近の有効な日付データが不足しています。")
                else:
                    st.info(f"⏳ あと {5 - len(df_clean)} 日分のデータを入力すると、直近のトレンドに基づいた目標達成予測が表示されます！")

            st.markdown("---")
            st.write("■ 朝の体重 (kg)")
            weight_line = alt.Chart(df_clean).mark_line(point=True).encode(
                x=alt.X('日付', title='日付', sort=None),
                y=alt.Y('朝の体重(kg)', scale=alt.Scale(zero=False), title='体重(kg)'),
                tooltip=['日付', '朝の体重(kg)']
            )
            target_w_rule = alt.Chart(pd.DataFrame({'target': [current_target_w]})).mark_rule(color='red', strokeDash=[5, 5]).encode(y='target')
            st.altair_chart(weight_line + target_w_rule, use_container_width=True)

            st.write("■ 体脂肪率 (%)")
            fat_line = alt.Chart(df_clean).mark_line(point=True, color='orange').encode(
                x=alt.X('日付', title='日付', sort=None),
                y=alt.Y('体脂肪率(%)', scale=alt.Scale(zero=False), title='体脂肪率(%)'),
                tooltip=['日付', '体脂肪率(%)']
            )
            target_f_rule = alt.Chart(pd.DataFrame({'target': [current_target_f]})).mark_rule(color='orange', strokeDash=[5, 5]).encode(y='target')
            st.altair_chart(fat_line + target_f_rule, use_container_width=True)
        else:
            st.info("有効な数値データがありません。")

        # --- 📋 過去データの一覧＆削除管理セクション ---
        st.markdown("---")
        st.subheader("📋 過去データの確認・削除")
        
        if 'カロリーマイナス(kcal)' in df.columns:
            latest_cals = df.dropna(subset=['カロリーマイナス(kcal)'])
            latest_cals = latest_cals[pd.to_numeric(latest_cals['カロリーマイナス(kcal)'], errors='coerce').notna()]
            if not latest_cals.empty:
                c_val = float(latest_cals.iloc[-1]['カロリーマイナス(kcal)'])
                c_date = latest_cals.iloc[-1]['日付']
                st.caption(f"💡 {c_date} の推定カロリーマイナス: {c_val:,.0f} kcal")

        st.dataframe(df, use_container_width=True)

        with st.expander("🗑️ データの削除を行う"):
            date_list = df['日付'].dropna().astype(str).tolist()
            if date_list:
                selected_date_to_delete = st.selectbox("削除したい日付を選択", date_list)
                if st.button("選択した日のデータを削除する", type="primary"):
                    try:
                        all_values = worksheet.get('A:N')
                        header = all_values[0]
                        rows = all_values[1:]
                        
                        new_rows = [row for row in rows if row and row[0].replace('-', '/') != selected_date_to_delete.replace('-', '/')]
                        
                        data_to_write = [header] + new_rows
                        worksheet.batch_clear(["A:N"])
                        try:
                            worksheet.update(range_name="A1", values=data_to_write)
                        except TypeError:
                            worksheet.update("A1", data_to_write)
                            
                        st.success(f"{selected_date_to_delete} のデータを削除しました！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"削除エラー: {e}")
            else:
                st.info("削除できるデータがありません。")

    else:
        st.info("データがありません。記録を追加すると一覧が表示されます。")