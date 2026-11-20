import pandas as pd, plotly.express as px, plotly.graph_objects as go, streamlit as st
st.set_page_config(page_title="Nassau Candy Route Efficiency", layout="wide")
FAC={"Lot's O' Nuts":(32.881893,-111.768036),"Wicked Choccy's":(32.076176,-81.088371),"Sugar Shack":(48.11914,-96.18115),
     "Secret Factory":(41.446333,-90.565487),"The Other Factory":(35.1175,-89.971107)}
S="AL Alabama|AK Alaska|AZ Arizona|AR Arkansas|CA California|CO Colorado|CT Connecticut|DE Delaware|DC District Of Columbia|FL Florida|GA Georgia|HI Hawaii|ID Idaho|IL Illinois|IN Indiana|IA Iowa|KS Kansas|KY Kentucky|LA Louisiana|ME Maine|MD Maryland|MA Massachusetts|MI Michigan|MN Minnesota|MS Mississippi|MO Missouri|MT Montana|NE Nebraska|NV Nevada|NH New Hampshire|NJ New Jersey|NM New Mexico|NY New York|NC North Carolina|ND North Dakota|OH Ohio|OK Oklahoma|OR Oregon|PA Pennsylvania|RI Rhode Island|SC South Carolina|SD South Dakota|TN Tennessee|TX Texas|UT Utah|VT Vermont|VA Virginia|WA Washington|WV West Virginia|WI Wisconsin|WY Wyoming"
ABBR={n:a for a,n in (p.split(" ",1) for p in S.split("|"))}

@st.cache_data
def load():
    # The uploaded CSV stores dates as DD-MM-YYYY (for example, 03-01-2024).
    # Parse explicitly so Pandas does not leave the columns as strings.
    df = pd.read_csv("shipments.csv")

    required = [
        "Row ID", "Order ID", "Order Date", "Ship Date", "Lead",
        "Ship Mode", "State/Province", "Region", "Factory", "City",
        "Product Name", "Sales", "Units", "Gross Profit", "Cost"
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        st.error("Your shipments.csv is missing these required columns: " + ", ".join(missing))
        st.stop()

    for col in ["Order Date", "Ship Date"]:
        df[col] = pd.to_datetime(
            df[col].astype(str).str.strip(),
            format="%d-%m-%Y",
            errors="coerce"
        )

    for col in ["Lead", "Sales", "Units", "Gross Profit", "Cost", "Row ID"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=[
        "Order Date", "Ship Date", "Lead", "Sales", "Units",
        "Gross Profit", "Cost", "Row ID"
    ]).copy()

    if df.empty:
        st.error("No valid shipment rows remain after reading the dates and numeric columns. Check shipments.csv.")
        st.stop()

    return df

raw = load()

st.title("🍬 Nassau Candy – Shipping Route Efficiency")
actual_gap = (raw["Ship Date"] - raw["Order Date"]).dt.days
gap_min, gap_max = int(actual_gap.min()), int(actual_gap.max())
if gap_max > 365:
    st.warning(
        f"Data caveat: Ship Dates in this file are {gap_min:,}–{gap_max:,} days after Order Dates. "
        "This is unusually long, including for Same Day shipments. Treat lead times as a relative "
        "comparison score, not as realistic delivery days, until the source dates are verified."
    )

# ---- sidebar filters
sb=st.sidebar; sb.header("Filters")
dmin,dmax=raw["Order Date"].min().date(),raw["Order Date"].max().date()
dr=sb.date_input("Order date range",(dmin,dmax),min_value=dmin,max_value=dmax)
if len(dr)!=2: st.stop()
regions=sb.multiselect("Region",sorted(raw.Region.unique()),default=sorted(raw.Region.unique()))
states=sb.multiselect("State / Province (blank = all)",sorted(raw["State/Province"].unique()))
modes=sb.multiselect("Ship mode",sorted(raw["Ship Mode"].unique()),default=sorted(raw["Ship Mode"].unique()))
d=raw[(raw["Order Date"].dt.date>=dr[0])&(raw["Order Date"].dt.date<=dr[1])&raw.Region.isin(regions)&raw["Ship Mode"].isin(modes)]
if states: d=d[d["State/Province"].isin(states)]
if d.empty: st.error("No shipments match the filters."); st.stop()
thr=sb.slider("Delay threshold (lead time ≥ X days)",int(raw.Lead.min()),int(raw.Lead.max()),int(raw.Lead.quantile(.75)))
d=d.assign(Delayed=(d.Lead>=thr).astype(int))

k=st.columns(5)
k[0].metric("Shipments",f"{len(d):,}"); k[1].metric("Avg lead time",f"{d.Lead.mean():,.1f}")
k[2].metric("Lead time std dev",f"{d.Lead.std():,.1f}"); k[3].metric("Delay frequency",f"{d.Delayed.mean():.1%}")
k[4].metric("Routes",d.groupby(["Factory","State/Province"]).ngroups)

def routes(x,by):
    g=x.groupby(["Factory",by]).agg(Shipments=("Row ID","count"),AvgLead=("Lead","mean"),Std=("Lead","std"),Delay=("Delayed","mean")).reset_index()
    g["Route"]=g.Factory+" → "+g[by]; g["Std"]=g.Std.fillna(0)
    lo,hi=g.AvgLead.min(),g.AvgLead.max(); g["Efficiency"]=100*(hi-g.AvgLead)/(hi-lo) if hi>lo else 100.0
    return g.sort_values("AvgLead").reset_index(drop=True)

t1,t2,t3,t4=st.tabs(["Route Efficiency","Geographic Map","Ship Mode Comparison","Route Drill-Down"])

with t1:
    c=st.columns(2); lvl=c[0].radio("Route level",["Region","State/Province"],horizontal=True)
    minv=c[1].slider("Minimum shipments per route",1,100,30 if lvl!="Region" else 1)
    r=routes(d,lvl); r=r[r.Shipments>=minv].reset_index(drop=True)
    if r.empty: st.info("No routes meet the minimum.")
    else:
        lo,hi=r.AvgLead.min(),r.AvgLead.max(); r["Efficiency"]=100*(hi-r.AvgLead)/(hi-lo) if hi>lo else 100.0
        show=r.head(25) if len(r)>25 else r
        st.plotly_chart(px.bar(show.iloc[::-1],x="AvgLead",y="Route",orientation="h",color="Efficiency",color_continuous_scale="RdYlGn",
            title="Average lead time by route (fastest 25 shown)",hover_data=["Shipments","Delay"]),width="stretch")
        fmt={"AvgLead":"{:,.1f}","Std":"{:,.1f}","Delay":"{:.1%}","Efficiency":"{:.1f}"}
        a,b=st.columns(2)
        a.subheader("🏆 Top 10 most efficient"); a.dataframe(r.head(10)[["Route","Shipments","AvgLead","Std","Delay","Efficiency"]].style.format(fmt),hide_index=True)
        b.subheader("🐢 Bottom 10 least efficient"); b.dataframe(r.tail(10).iloc[::-1][["Route","Shipments","AvgLead","Std","Delay","Efficiency"]].style.format(fmt),hide_index=True)
        with st.expander("Full leaderboard"): st.dataframe(r.style.format(fmt),hide_index=True)

with t2:
    s=d.groupby("State/Province").agg(Shipments=("Row ID","count"),AvgLead=("Lead","mean"),Delay=("Delayed","mean")).reset_index()
    s["Abbr"]=s["State/Province"].map(ABBR); su=s.dropna(subset=["Abbr"])
    fig=px.choropleth(su,locations="Abbr",locationmode="USA-states",color="AvgLead",scope="usa",color_continuous_scale="RdYlGn_r",
        hover_name="State/Province",hover_data={"Abbr":False,"Shipments":True,"Delay":":.1%"},title="Average lead time by customer state (red = slower)")
    fig.add_trace(go.Scattergeo(lon=[v[1] for v in FAC.values()],lat=[v[0] for v in FAC.values()],text=list(FAC),mode="markers+text",
        textposition="top center",marker=dict(size=11,color="black",symbol="star"),name="Factories"))
    st.plotly_chart(fig,width="stretch")
    st.subheader("Regional bottlenecks")
    g=d.groupby("Region").agg(Shipments=("Row ID","count"),AvgLead=("Lead","mean"),Delay=("Delayed","mean")).reset_index()
    g["Flag"]=["BOTTLENECK" if (x.Shipments>=g.Shipments.median() and x.AvgLead>d.Lead.mean() and x.Delay>d.Delayed.mean()) else "OK" for x in g.itertuples()]
    st.dataframe(g.style.format({"AvgLead":"{:,.1f}","Delay":"{:.1%}"}),hide_index=True)
    sv=s[s.Shipments>=s.Shipments.median()].sort_values("AvgLead",ascending=False).head(10)
    st.subheader("Congestion-prone states (high volume, slowest first)")
    st.dataframe(sv.drop(columns="Abbr").style.format({"AvgLead":"{:,.1f}","Delay":"{:.1%}"}),hide_index=True)

with t3:
    m=d.groupby("Ship Mode").agg(Shipments=("Row ID","count"),AvgLead=("Lead","mean"),Delay=("Delayed","mean"),Cost=("Cost","sum"),Units=("Units","sum"),Sales=("Sales","sum"),Profit=("Gross Profit","sum")).reset_index()
    m["CostPerUnit"]=m.Cost/m.Units; m["Margin"]=m.Profit/m.Sales
    a,b=st.columns(2)
    a.plotly_chart(px.bar(m,x="Ship Mode",y="AvgLead",color="Ship Mode",title="Average lead time"),width="stretch")
    b.plotly_chart(px.bar(m,x="Ship Mode",y="Delay",color="Ship Mode",title="Delay frequency").update_yaxes(tickformat=".0%"),width="stretch")
    st.plotly_chart(px.scatter(m,x="CostPerUnit",y="AvgLead",size="Shipments",color="Ship Mode",title="Cost–time tradeoff (descriptive; Cost = manufacturing cost, no freight)"),width="stretch")
    st.dataframe(m.style.format({"AvgLead":"{:,.1f}","Delay":"{:.1%}","CostPerUnit":"${:.2f}","Margin":"{:.1%}","Cost":"${:,.0f}","Sales":"${:,.0f}","Profit":"${:,.0f}"}),hide_index=True)
    d2=d.assign(Group=d["Ship Mode"].where(d["Ship Mode"]=="Standard Class","Expedited").replace("Standard Class","Standard"))
    st.subheader("Standard vs Expedited")
    st.dataframe(d2.groupby("Group").agg(Shipments=("Row ID","count"),AvgLead=("Lead","mean"),Delay=("Delayed","mean")).reset_index().style.format({"AvgLead":"{:,.1f}","Delay":"{:.1%}"}),hide_index=True)

with t4:
    opts=sorted(d["State/Province"].unique()); sel=st.selectbox("State / Province",opts)
    x=d[d["State/Province"]==sel]
    c=st.columns(4); c[0].metric("Shipments",len(x)); c[1].metric("Avg lead",f"{x.Lead.mean():,.1f}"); c[2].metric("Std dev",f"{x.Lead.std():,.1f}" if len(x)>1 else "–"); c[3].metric("Delay freq",f"{x.Delayed.mean():.1%}")
    st.dataframe(routes(x,"State/Province")[["Route","Shipments","AvgLead","Std","Delay","Efficiency"]].style.format({"AvgLead":"{:,.1f}","Std":"{:,.1f}","Delay":"{:.1%}","Efficiency":"{:.1f}"}),hide_index=True)
    st.plotly_chart(px.box(x,x="Ship Mode",y="Lead",color="Factory",title=f"Lead time distribution – {sel}"),width="stretch")
    n=st.slider("Orders in timeline",5,50,20); o=x.sort_values("Order Date").head(n).copy(); o["Label"]=o["Order ID"]+" ("+o["Ship Mode"]+")"
    st.plotly_chart(px.timeline(o,x_start="Order Date",x_end="Ship Date",y="Label",color="Factory",title="Order-level shipment timeline (order → ship)").update_yaxes(autorange="reversed"),width="stretch")
    with st.expander("Order-level data"): st.dataframe(x[["Order ID","Order Date","Ship Date","Lead","Ship Mode","City","Factory","Product Name","Sales"]],hide_index=True)
