import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------
# ✅ PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="BMI Calculator",
    page_icon="📊",
    layout="centered"
)

st.title("📊 BMI Calculator")
st.write("Calculate your Body Mass Index with a color-coded result + chart.")

# ---------------------------------------------------------
# ✅ USER INPUT
# ---------------------------------------------------------
st.header("Enter Your Details")

col1, col2 = st.columns(2)

with col1:
    height = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=165.0)

with col2:
    weight = st.number_input("Weight (kg)", min_value=10.0, max_value=200.0, value=60.0)

if st.button("Calculate BMI"):
    # ---------------------------------------------------------
    # ✅ BMI CALCULATION
    # ---------------------------------------------------------
    height_m = height / 100
    bmi = weight / (height_m ** 2)
    bmi = round(bmi, 2)

    # ---------------------------------------------------------
    # ✅ Determine BMI Category + Color Tag
    # ---------------------------------------------------------
    if bmi < 18.5:
        category = "Underweight"
        color = "#3498db"     # blue
    elif 18.5 <= bmi < 24.9:
        category = "Normal"
        color = "#2ecc71"     # green
    elif 25 <= bmi < 29.9:
        category = "Overweight"
        color = "#f1c40f"     # yellow
    else:
        category = "Obese"
        color = "#e74c3c"     # red

    # ---------------------------------------------------------
    # ✅ Show BMI Result
    # ---------------------------------------------------------
    st.subheader("Your BMI Result")
    st.markdown(
        f"""
        <div style="padding: 15px; background-color: {color}; color: white; 
        text-align: center; border-radius: 8px;">
            <h3>BMI: {bmi}</h3>
            <h4>{category}</h4>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ---------------------------------------------------------
    # ✅ BMI RANGE CHART (Plotly)
    # ---------------------------------------------------------
    st.subheader("BMI Category Chart")

    df = pd.DataFrame({
        "Category": ["Underweight", "Normal", "Overweight", "Obese"],
        "BMI Range": [18.4, 24.9, 29.9, 40],   # Upper range values
        "Color": ["blue", "green", "yellow", "red"]
    })

    fig = px.bar(
        df,
        x="Category",
        y="BMI Range",
        color="Category",
        color_discrete_map={
            "Underweight": "blue",
            "Normal": "green",
            "Overweight": "yellow",
            "Obese": "red"
        },
        title="BMI Category Ranges",
    )

    fig.add_hline(y=bmi, line_dash="dot", line_color="black")
    fig.add_annotation(
        x=1.5,
        y=bmi,
        text=f"Your BMI: {bmi}",
        showarrow=True,
        arrowhead=1
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# ✅ FOOTER
# ---------------------------------------------------------
st.markdown("---")
st.write("Made with ❤️ using Streamlit")

