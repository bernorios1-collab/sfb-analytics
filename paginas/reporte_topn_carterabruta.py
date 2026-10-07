import io
import os
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.express as px
from config_db import obtener_engine
from sqlalchemy import text
from scrapers.indicadores_bcb import obtener_indicadores_bcb

# Importaciones para generación independiente de PDF con ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame, NextPageTemplate,
    Paragraph, Spacer, Table, TableStyle, Image, PageBreak, Flowable
)
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(text(query), engine, params=params)
    except Exception as e:
        st.error(f"Error al consultar la base de datos: {e}")
        return pd.DataFrame()

# ==========================================
# FUNCIÓN DE PDF TRADICIONAL VERTICAL
# ==========================================
def generar_pdf_reporte(df_topn, df_conc_ambito, fig_barras, fig_hist, grupo_sel, fecha_sel, top_n, nombre_moneda, total_cartera_grupo, total_sistema_nacional=None, ver_conc_tabla=False, ver_topn_tabla=False, ver_hist_tabla=False, cant_periodos=12, df_hist=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    elementos = []
    estilos = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('TituloPDF', parent=estilos['Heading1'], fontSize=13, leading=16, textColor=colors.HexColor('#002b49'), spaceAfter=3)
    estilo_sub = ParagraphStyle('SubPDF', parent=estilos['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#555555'), spaceAfter=8)
    estilo_h2 = ParagraphStyle('H2PDF', parent=estilos['Heading2'], fontSize=10, leading=13, textColor=colors.HexColor('#002b49'), spaceBefore=6, spaceAfter=4)
    estilo_descargo = ParagraphStyle('DescargoPDF', parent=estilos['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#444444'), spaceBefore=8, spaceAfter=4)
    estilo_celda_texto = ParagraphStyle('CeldaTextoPDF', parent=estilos['Normal'], fontSize=7.5, leading=9.5, textColor=colors.HexColor('#000000'))

    cant_real = len(df_topn)
    monto_topn = df_topn['Cartera Bruta'].sum()

    elementos.append(Paragraph(f"<b>Reporte Ejecutivo: Análisis Top {cant_real} Líderes en Cartera Bruta</b>", estilo_titulo))
    elementos.append(Paragraph(f"Ámbito: <b>{grupo_sel}</b> | Corte: <b>{fecha_sel}</b> | Histórico: <b>{cant_periodos} periodos</b> | Moneda: <b>{nombre_moneda}</b>", estilo_sub))

    elementos.append(Paragraph(f"<b>Concentración de Cartera: Top {cant_real} vs. Resto</b>", estilo_h2))
    try:
        color_top, color_resto = '#004a99', '#a6a6a6'
        mapa_colores = {f"Top {cant_real} Seleccionado": color_top, "Resto del Ámbito": color_resto, "Resto del Sistema Nacional": color_resto}

        def crear_torta_pdf(total_val, titulo_torta):
            df_pie = pd.DataFrame([
                {"Cat": f"Top {cant_real} Seleccionado", "Monto": monto_topn},
                {"Cat": titulo_torta, "Monto": max(0.0, total_val - monto_topn)}
            ])
            t_titulo = f"Concentración en Ámbito:<br><b>{grupo_sel}</b>" if "Ámbito" in titulo_torta else "Concentración en Total:<br><b>SISTEMA FINANCIERO NACIONAL</b>"
            fig = px.pie(df_pie, names="Cat", values="Monto", hole=0.42, color="Cat", color_discrete_map=mapa_colores, title=t_titulo)
            fig.update_traces(textinfo='label+percent', textposition='inside', textfont=dict(size=10))
            fig.update_layout(height=210, margin=dict(l=5, r=5, t=35, b=5), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title_font_size=9.5)
            return io.BytesIO(fig.to_image(format="png", width=480, height=210, scale=2))

        img1_bytes = crear_torta_pdf(total_cartera_grupo, "Resto del Ámbito")
        if total_sistema_nacional and total_sistema_nacional > 0:
            img2_bytes = crear_torta_pdf(total_sistema_nacional, "Resto del Sistema Nacional")
            t_tortas = Table([[Image(img1_bytes, width=272, height=140), Image(img2_bytes, width=272, height=140)]], colWidths=[276, 276])
            t_tortas.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
            elementos.append(t_tortas)
        else:
            t_unica = Table([[Image(img1_bytes, width=360, height=160)]], colWidths=[552])
            t_unica.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
            elementos.append(t_unica)
    except Exception as e:
        elementos.append(Paragraph(f"<i>[Error al renderizar gráficos de torta: {e}]</i>", estilo_sub))

    elementos.append(Spacer(1, 4))

    if ver_conc_tabla:
        df_conc_tabla = pd.concat([df_conc_ambito, pd.DataFrame([{"Entidad / Categoría": "TOTAL", "Monto": total_cartera_grupo, "Participación de Mercado (%)": 100.00}])], ignore_index=True)
        df_conc_data = [["Entidad / Categoría", "Monto", "Part. (%)"]] + [
            [Paragraph(str(r['Entidad / Categoría']), estilo_celda_texto), f"{r['Monto']:,.2f}", f"{r['Participación de Mercado (%)']:.2f}%"] for _, r in df_conc_tabla.iterrows()
        ]
        t_c = Table(df_conc_data, colWidths=[312, 140, 100])
        t_c.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#004a99')), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('ALIGN', (0,1), (0,-1), 'LEFT'), ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 7.5),
            ('BOTTOMPADDING', (0,0), (-1,0), 3), ('TOPPADDING', (0,0), (-1,-1), 3), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ]))
        elementos.extend([t_c, Spacer(1, 4)])

    elementos.append(Paragraph(f"<b>Estructura de Cartera Bruta - Top {cant_real} ({nombre_moneda})</b>", estilo_h2))
    try:
        df_pdf_bar = df_topn.iloc[::-1].copy()
        df_pdf_bar['etiqueta_extendida'] = df_pdf_bar['sigla']
        fig_pdf_bar = px.bar(
            df_pdf_bar, y='etiqueta_extendida', x=['Vigente', 'Vencida', 'Ejecución'], orientation='h', 
            color_discrete_sequence=['#1f77b4', '#d62728', '#ff7f0e'], 
            labels={'value': f'Monto ({nombre_moneda})', 'etiqueta_extendida': '', 'variable': 'Estado'}
        )
        fig_pdf_bar.update_layout(
            height=150, 
            margin=dict(l=60, r=10, t=10, b=25), 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(tickfont=dict(size=7.5), title=dict(font=dict(size=7.5), text=f"Monto ({nombre_moneda})")), 
            yaxis=dict(tickfont=dict(size=8)), 
            legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1, font=dict(size=7))
        )
        elementos.append(Image(io.BytesIO(fig_pdf_bar.to_image(format="png", width=520, height=150, scale=2)), width=510, height=145))
    except Exception as e:
        elementos.append(Paragraph(f"<i>[Error al renderizar gráfico de barras: {e}]</i>", estilo_sub))

    elementos.append(Spacer(1, 4))

    if ver_topn_tabla:
        elementos.append(Paragraph(f"<b>Detalle del Top {cant_real}</b>", estilo_h2))
        tabla_data = [["Puesto", "Sigla", "Entidad", "Cartera Bruta", "Part. (%)"]] + [
            [
                str(int(r['Posición'])), 
                str(r['sigla']), 
                Paragraph(str(r['nombre_completo']), estilo_celda_texto), 
                f"{r['Cartera Bruta']:,.2f}", 
                f"{r['Participación de Mercado (%)']:.2f}%"
            ] for _, r in df_topn.iterrows()
        ]
        t = Table(tabla_data, colWidths=[40, 45, 277, 95, 95])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#004a99')), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('ALIGN', (2,1), (2,-1), 'LEFT'), ('ALIGN', (3,1), (4,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 7.5),
            ('BOTTOMPADDING', (0,0), (-1,0), 3), ('TOPPADDING', (0,0), (-1,-1), 3), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ]))
        elementos.extend([t, Spacer(1, 4)])

    if fig_hist is not None:
        elementos.append(Paragraph(f"<b>Comportamiento Histórico del Top {cant_real} (Últimos {cant_periodos} Periodos)</b>", estilo_h2))
        try:
            fig_pdf_hist = px.line(
                df_hist, x='fecha_corte', y='monto', color='sigla', markers=True, 
                labels={'monto': f'Monto ({nombre_moneda})', 'fecha_corte': '', 'sigla': 'Entidad'}, 
                color_discrete_sequence=px.colors.qualitative.Set2
            ) if (df_hist is not None and not df_hist.empty) else fig_hist
            
            fig_pdf_hist.update_layout(
                height=140, 
                margin=dict(l=55, r=70, t=10, b=20), 
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                xaxis=dict(tickfont=dict(size=7), title=dict(text='')), 
                yaxis=dict(tickfont=dict(size=7), title=dict(text=f"Monto ({nombre_moneda})", font=dict(size=7))), 
                legend=dict(font=dict(size=6.5), itemwidth=30)
            )
            elementos.append(Image(io.BytesIO(fig_pdf_hist.to_image(format="png", width=520, height=140, scale=2)), width=510, height=135))
        except Exception as e:
            elementos.append(Paragraph(f"<i>[Error al renderizar gráfico histórico: {e}]</i>", estilo_sub))
        elementos.append(Spacer(1, 4))

        if ver_hist_tabla and df_hist is not None and not df_hist.empty:
            df_pivot_hist = df_hist.pivot(index='fecha_corte', columns='sigla', values='monto').sort_index(ascending=False)
            df_pivot_hist.index = df_pivot_hist.index.strftime('%Y-%m-%d')
            hist_data = [["Fecha"] + list(df_pivot_hist.columns)] + [[str(idx)] + [f"{val:,.2f}" if pd.notnull(val) else "-" for val in row] for idx, row in df_pivot_hist.iterrows()]
            col_w = [65] + [float(487 / max(1, len(df_pivot_hist.columns)))] * len(df_pivot_hist.columns)
            t_h = Table(hist_data, colWidths=col_w)
            t_h.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#004a99')), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 6.5),
                ('BOTTOMPADDING', (0,0), (-1,0), 3), ('TOPPADDING', (0,0), (-1,-1), 3), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
            ]))
            elementos.append(t_h)

    elementos.append(Paragraph("<b>Nota de Descargo:</b> Los datos mostrados proceden de los Boletines Estadísticos Oficiales de la ASFI (información pública). Esta información se difunde con fines estrictamente analíticos e informativos; no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión.", estilo_descargo))
    
    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()


# ==========================================
# FUNCIÓN DE PRESENTACIÓN EN LÁMINAS CUADRADAS (ESTILO EJECUTIVO PREMIUM)
# ==========================================
def generar_pdf_laminas(df_topn, df_conc_ambito, fig_barras, fig_hist, grupo_sel, fecha_sel, top_n, nombre_moneda, total_cartera_grupo, total_sistema_nacional=None, ver_conc_tabla=False, ver_topn_tabla=False, ver_hist_tabla=False, cant_periodos=12, df_hist=None):
    from reportlab.pdfgen import canvas

    # --- Paleta e identidad visual de la presentación ---
    NAVY = colors.HexColor('#0b2340')       # fondo portada / cierre
    NAVY_2 = colors.HexColor('#002b49')     # texto / marca principal
    NAVY_SOFT = colors.HexColor('#12325a')  # tarjetas sobre fondo oscuro
    GOLD = colors.HexColor('#f5a623')       # acento
    LIGHT_BG = colors.HexColor('#f5f7fb')   # fondo láminas de contenido
    CARD_BG = colors.white
    MUTED = colors.HexColor('#64748b')
    MUTED_LT = colors.HexColor('#c7d2e0')
    GRID_LN = colors.HexColor('#dde4ee')
    SERIE_COLORS = ['#1f77b4', '#d62728', '#ff7f0e']

    PAGE = 540
    MARGIN = 26
    FOOTER_ZONE = 30
    y0 = MARGIN + FOOTER_ZONE
    frame_h = PAGE - y0 - MARGIN

    buffer = io.BytesIO()
    estilos = getSampleStyleSheet()

    def crear_estilo(nombre, **kw):
        base = dict(parent=estilos['Normal'], fontName='Helvetica')
        base.update(kw)
        return ParagraphStyle(nombre, **base)

    st_kicker_dark = crear_estilo('KickerDark', fontSize=8, leading=10, textColor=GOLD, fontName='Helvetica-Bold')
    st_titulo_dark = crear_estilo('TitDark', fontSize=21, leading=25, textColor=colors.white, fontName='Helvetica-Bold', spaceAfter=6)
    st_sub_dark = crear_estilo('SubDark', fontSize=9.5, leading=13, textColor=MUTED_LT, spaceAfter=4)
    st_titulo_light = crear_estilo('TitLight', fontSize=15.5, leading=19, textColor=NAVY_2, fontName='Helvetica-Bold', spaceAfter=3)
    st_sub_light = crear_estilo('SubLight', fontSize=8.5, leading=11, textColor=MUTED, spaceAfter=8)
    st_celda = crear_estilo('Celda', fontSize=6.8, leading=8.8, textColor=colors.HexColor('#0f172a'))
    st_aclaracion = crear_estilo('Aclara', fontSize=6.8, leading=9, textColor=colors.HexColor('#334155'))
    st_despedida = crear_estilo('Desp', fontSize=10.5, leading=15, alignment=1, textColor=colors.white)
    st_descargo = crear_estilo('DescT', fontSize=9.2, leading=13.2, textColor=colors.HexColor('#334155'))

    def st_stat_val(color, size=19):
        return crear_estilo(
            'StatVal%s_%s' % (id(color), size),
            fontSize=size,
            leading=size + 2,
            textColor=color,
            fontName='Helvetica-Bold',
            alignment=1
        )

    def st_stat_lbl(color):
        return crear_estilo('StatLbl%s' % id(color), fontSize=7, leading=9, textColor=color, alignment=1)

    cant_real = len(df_topn)
    monto_topn = df_topn['Cartera Bruta'].sum()

    # ---------- pequeños "flowables" de identidad visual ----------
    class Chip(Flowable):
        def __init__(self, text, bg, fg, font_size=7.2, pad=9, height=15):
            super().__init__()
            self.text, self.bg, self.fg = text, bg, fg
            self.font_size, self.pad, self.height = font_size, pad, height
            self.width = stringWidth(text, 'Helvetica-Bold', font_size) + pad * 2

        def wrap(self, aw, ah):
            return self.width, self.height

        def draw(self):
            c = self.canv
            c.saveState()
            c.setFillColor(self.bg)
            c.roundRect(0, 0, self.width, self.height, self.height / 2, fill=1, stroke=0)
            c.setFillColor(self.fg)
            c.setFont('Helvetica-Bold', self.font_size)
            c.drawCentredString(self.width / 2, self.height / 2 - self.font_size * 0.35, self.text)
            c.restoreState()

    def stat_card(valor, etiqueta, bg, val_color, lbl_color, w, val_size=19):
        data = [[Paragraph(valor, st_stat_val(val_color, val_size))], [Paragraph(etiqueta, st_stat_lbl(lbl_color))]]
        t = Table(data, colWidths=[w])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg),
            ('TOPPADDING', (0, 0), (0, 0), 12), ('BOTTOMPADDING', (0, 0), (0, 0), 1),
            ('TOPPADDING', (0, 1), (0, 1), 0), ('BOTTOMPADDING', (0, 1), (0, 1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        return t

    def card_wrap(contenido, w, pad=10, bg=CARD_BG, border=GRID_LN, border_w=0.75):
        celda = contenido if isinstance(contenido, list) else [contenido]
        t = Table([[celda]], colWidths=[w])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg),
            ('BOX', (0, 0), (-1, -1), border_w, border),
            ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
            ('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
        ]))
        return t

    # ---------- identidad de marca ----------
    def resolver_logo_path():
        candidatos = []
        try:
            carpeta_script = Path(__file__).resolve().parent
            candidatos.append(carpeta_script / "imagenes" / "logotipo.png")
            for padre in carpeta_script.parents:
                candidatos.append(padre / "imagenes" / "logotipo.png")
        except Exception:
            pass
        candidatos.append(Path.cwd() / "imagenes" / "logotipo.png")
        for candidato in candidatos:
            try:
                if candidato.is_file():
                    return str(candidato)
            except Exception:
                continue
        return None

    LOGO_PATH = resolver_logo_path()

    def draw_logo(cnv, fondo_oscuro=False, logo_w=88, y_top=22):
        if not LOGO_PATH:
            return
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            logo_h = logo_w * ih / iw if iw else 24
            x = PAGE - MARGIN - logo_w
            y = PAGE - y_top - logo_h
            cnv.drawImage(
                img, x, y, width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask='auto'
            )
        except Exception:
            pass

    # ---------- fondos y "chrome" de cada tipo de lámina ----------
    def draw_cover_bg(cnv, _doc):
        cnv.saveState()
        cnv.setFillColor(NAVY)
        cnv.rect(0, 0, PAGE, PAGE, fill=1, stroke=0)
        cnv.setFillColor(NAVY_SOFT)
        cnv.setFillAlpha(0.55)
        cnv.circle(PAGE - 20, PAGE, 150, fill=1, stroke=0)
        cnv.setFillAlpha(1)
        cnv.setStrokeColor(GOLD)
        cnv.setLineWidth(1.3)
        cnv.line(MARGIN, 38, PAGE - MARGIN, 38)
        
        if cnv._pageNumber == 1:
            draw_logo(cnv, fondo_oscuro=True)
            
        cnv.restoreState()

    def draw_content_bg(cnv, _doc):
        cnv.saveState()
        cnv.setFillColor(LIGHT_BG)
        cnv.rect(0, 0, PAGE, PAGE, fill=1, stroke=0)
        cnv.setFillColor(NAVY_2)
        cnv.rect(0, 0, 6, PAGE, fill=1, stroke=0)
        cnv.setStrokeColor(GOLD)
        cnv.setLineWidth(1.3)
        cnv.line(MARGIN, 38, PAGE - MARGIN, 38)
        cnv.restoreState()

    frame_cover = Frame(MARGIN, y0, PAGE - 2 * MARGIN, frame_h, id='f_cover', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_content = Frame(MARGIN + 10, y0, PAGE - 2 * MARGIN - 10, frame_h, id='f_content', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(
        buffer, pagesize=(PAGE, PAGE), leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
        pageTemplates=[
            PageTemplate(id='cover', frames=[frame_cover], onPage=draw_cover_bg),
            PageTemplate(id='content', frames=[frame_content], onPage=draw_content_bg),
        ]
    )

    elementos = []

    # ==========================================
    # LÁMINA 1: PORTADA EJECUTIVA
    # ==========================================
    elementos.append(Chip("REPORTE GERENCIAL", GOLD, NAVY_2))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(f"Top {cant_real} Líderes en Cartera Bruta", st_titulo_dark))
    elementos.append(Paragraph(
        f"Contraste: Top {cant_real} vs. Resto de su Ámbito ({grupo_sel})",
        st_sub_dark
    ))
    elementos.append(Paragraph(
        f"Ámbito: <b>{grupo_sel}</b>  |  Corte: <b>{fecha_sel}</b>  |  Moneda: <b>{nombre_moneda}</b>",
        st_sub_dark
    ))
    elementos.append(Spacer(1, 10))

    share_topn_amb = (monto_topn / total_cartera_grupo * 100) if total_cartera_grupo > 0 else 0.0
    w_stat_side = 124
    w_stat_center = 218
    gap_stat = 7
    tarjetas = Table([[
        stat_card(
            f"{share_topn_amb:.1f}%",
            f"Concentración<br/>del Top {cant_real}",
            NAVY_SOFT, GOLD, colors.white, w_stat_side, val_size=18
        ),
        '',
        stat_card(
            f"{monto_topn:,.0f}",
            f"Cartera Top {cant_real}<br/>({nombre_moneda})",
            NAVY_SOFT, GOLD, colors.white, w_stat_center, val_size=24
        ),
        '',
        stat_card(
            str(cant_real),
            "Entidades<br/>Analizadas",
            NAVY_SOFT, GOLD, colors.white, w_stat_side, val_size=18
        ),
    ]], colWidths=[w_stat_side, gap_stat, w_stat_center, gap_stat, w_stat_side])
    tarjetas.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    elementos.append(tarjetas)
    elementos.append(Spacer(1, 16))

    try:
        # MEJORA SOLICITADA: Gráfico de torta de la portada ajustado al ámbito propio
        df_pie_portada = pd.DataFrame([
            {"Cat": f"Top {cant_real} Seleccionado", "Monto": monto_topn},
            {"Cat": f"Resto del Ámbito", "Monto": max(0.0, total_cartera_grupo - monto_topn)}
        ])
        fig_p = px.pie(df_pie_portada, names="Cat", values="Monto", hole=0.55, color="Cat",
                        color_discrete_map={f"Top {cant_real} Seleccionado": '#f5a623', "Resto del Ámbito": '#3a5578'})
        fig_p.update_traces(textinfo='label+percent', textposition='inside', textfont=dict(size=10.5, color='white'))
        fig_p.update_layout(height=270, margin=dict(l=4, r=4, t=6, b=4), showlegend=False,
                             paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        img_portada = Image(
            io.BytesIO(fig_p.to_image(format="png", width=500, height=270, scale=2)),
            width=430, height=232
        )
        elementos.append(Table(
            [[img_portada]],
            colWidths=[488],
            style=TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')])
        ))
    except Exception:
        pass

    elementos.append(NextPageTemplate('content'))
    elementos.append(PageBreak())

    # ==========================================
    # LÁMINA 2: CONCENTRACIÓN DE MERCADO
    # ==========================================
    elementos.append(Chip("CONCENTRACIÓN DE MERCADO", NAVY_2, colors.white))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(f"Concentración de Cartera: Top {cant_real} vs. Resto del Sistema Financiero Nacional Regulado", st_titulo_light))
    elementos.append(Paragraph(f"Ámbito: {grupo_sel}  |  Corte: {fecha_sel}  |  Moneda: {nombre_moneda}", st_sub_light))

    try:
        h_tortas = 305 if not ver_conc_tabla else 178
        img_w = 238 if not ver_conc_tabla else 214
        etiqueta_top = f"Top {cant_real} Sel."

        def crear_torta_lamina(total_val, titulo_torta):
            df_pie = pd.DataFrame([
                {"Cat": etiqueta_top, "Monto": monto_topn},
                {"Cat": titulo_torta, "Monto": max(0.0, total_val - monto_topn)}
            ])
            t_titulo = f"En Ámbito<br>{grupo_sel}" if "Ámbito" in titulo_torta else "En Sistema Financiero Nacional Regulado"
            fig = px.pie(
                df_pie, names="Cat", values="Monto", hole=0.5, color="Cat",
                color_discrete_map={etiqueta_top: '#004a99', titulo_torta: '#cbd5e1'},
                title=t_titulo
            )
            fig.update_traces(textinfo='label+percent', textposition='inside', textfont=dict(size=10))
            fig.update_layout(
                height=h_tortas,
                margin=dict(l=4, r=4, t=30, b=4),
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                title_font_size=10,
                title_font_color='#002b49'
            )
            return io.BytesIO(
                fig.to_image(format="png", width=360, height=h_tortas, scale=2)
            )

        if total_sistema_nacional and total_sistema_nacional > 0:
            img1_b = crear_torta_lamina(total_cartera_grupo, "Resto Ámbito")
            img2_b = crear_torta_lamina(total_sistema_nacional, "Resto del Sistema Financiero Nacional Regulado")
            celdas = [
                Image(img1_b, width=img_w, height=h_tortas * 0.92),
                Image(img2_b, width=img_w, height=h_tortas * 0.92)
            ]
            anchos = [244, 244]
        else:
            img_w_solo = 420 if not ver_conc_tabla else 300
            img1_b = crear_torta_lamina(total_cartera_grupo, "Resto Ámbito")
            celdas = [Image(img1_b, width=img_w_solo, height=h_tortas * 0.92)]
            anchos = [488]

        t_tortas = Table([celdas], colWidths=anchos)
        t_tortas.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        t_tortas.hAlign = 'CENTER'
        elementos.append(card_wrap(t_tortas, w=488, pad=5))
    except Exception:
        pass

    elementos.append(Spacer(1, 8))

    if ver_conc_tabla:
        df_conc_tabla_l = pd.concat([df_conc_ambito, pd.DataFrame([{"Entidad / Categoría": "TOTAL", "Monto": total_cartera_grupo, "Participación de Mercado (%)": 100.00}])], ignore_index=True)
        tabla_lamina_data = [["Entidad / Categoría", "Monto", "Part. (%)"]] + [
            [str(r['Entidad / Categoría']), f"{r['Monto']:,.2f}", f"{r['Participación de Mercado (%)']:.2f}%"] for _, r in df_conc_tabla_l.iterrows()
        ]
        t_lam_c = Table(tabla_lamina_data, colWidths=[268, 120, 100])
        t_lam_c.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY_2), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('ALIGN', (0, 1), (0, -1), 'LEFT'), ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID_LN),
        ]))
        elementos.append(card_wrap(t_lam_c, w=488, pad=0))

    elementos.append(PageBreak())

    # ==========================================
    # LÁMINA 3: ESTRUCTURA DE CARTERA
    # ==========================================
    elementos.append(Chip("ESTRUCTURA DE CARTERA", NAVY_2, colors.white))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(f"Estructura de Cartera Bruta — Top {cant_real} Líderes", st_titulo_light))
    elementos.append(Paragraph(f"Ámbito: {grupo_sel}  |  Corte: {fecha_sel}  |  Moneda: {nombre_moneda}", st_sub_light))

    try:
        df_lam_bar = df_topn.iloc[::-1].copy()
        df_lam_bar['etq'] = df_lam_bar['sigla']
        fig_l_bar = px.bar(df_lam_bar, y='etq', x=['Vigente', 'Vencida', 'Ejecución'], orientation='h',
                            color_discrete_sequence=SERIE_COLORS,
                            labels={'value': f'Monto ({nombre_moneda})', 'etq': '', 'variable': 'Estado'})
        h_bar = 300 if not ver_topn_tabla else 155
        fig_l_bar.update_layout(height=h_bar, margin=dict(l=40, r=10, t=10, b=25),
                                 paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                 xaxis=dict(tickfont=dict(size=8.5), title=dict(font=dict(size=9), text=f"Monto ({nombre_moneda})")),
                                 yaxis=dict(tickfont=dict(size=8.5, color='#002b49'), title=dict(text='')),
                                 legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1, font=dict(size=8)))
        img_bar = Image(io.BytesIO(fig_l_bar.to_image(format="png", width=500, height=h_bar, scale=2)), width=478, height=h_bar - 6)
        elementos.append(card_wrap(img_bar, w=488))
    except Exception:
        pass

    elementos.append(Spacer(1, 6))

    aclaraciones_texto = "<b>Siglas:</b> " + "  ·  ".join([f"<b>{r['sigla']}</b> {r['nombre_completo']}" for _, r in df_topn.iterrows()])
    elementos.append(card_wrap(Paragraph(aclaraciones_texto, st_aclaracion), w=488, pad=8, bg=LIGHT_BG))
    elementos.append(Spacer(1, 6))

    if ver_topn_tabla:
        tabla_lam_topn = [["Puesto", "Sigla", "Entidad", "Cartera Bruta", "Part. (%)"]] + [
            [str(int(r['Posición'])), str(r['sigla']), Paragraph(str(r['nombre_completo']), st_celda),
             f"{r['Cartera Bruta']:,.2f}", f"{r['Participación de Mercado (%)']:.2f}%"] for _, r in df_topn.iterrows()
        ]
        t_lam_t = Table(tabla_lam_topn, colWidths=[30, 38, 247, 88, 85])
        t_lam_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY_2), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('ALIGN', (2, 1), (2, -1), 'LEFT'), ('ALIGN', (3, 1), (4, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 6.5),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID_LN),
        ]))
        elementos.append(card_wrap(t_lam_t, w=488, pad=0))

    elementos.append(PageBreak())

    # ==========================================
    # LÁMINA 4: COMPORTAMIENTO HISTÓRICO
    # ==========================================
    elementos.append(Chip("TENDENCIA HISTÓRICA", NAVY_2, colors.white))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(f"Comportamiento Histórico del Top {cant_real}", st_titulo_light))
    elementos.append(Paragraph(f"Ámbito: {grupo_sel}  |  Corte: {fecha_sel}  |  Moneda: {nombre_moneda}  |  Evolución en los últimos {cant_periodos} periodos", st_sub_light))

    h_hist = 265 if not (ver_hist_tabla and df_hist is not None and not df_hist.empty) else 152
    try:
        fig_l_hist = px.line(
            df_hist, x='fecha_corte', y='monto', color='sigla', markers=True,
            labels={'monto': f'Monto ({nombre_moneda})', 'fecha_corte': '', 'sigla': 'Entidad'},
            color_discrete_sequence=px.colors.qualitative.Set2
        ) if (df_hist is not None and not df_hist.empty) else fig_hist

        if fig_l_hist is not None:
            fig_l_hist.update_layout(
                height=h_hist,
                margin=dict(l=50, r=45, t=10, b=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(tickfont=dict(size=8.5), title=dict(text='')),
                yaxis=dict(
                    tickfont=dict(size=8.5),
                    title=dict(text=f"Monto ({nombre_moneda})", font=dict(size=9))
                ),
                legend=dict(font=dict(size=7), itemwidth=25)
            )
            try:
                png_hist = fig_l_hist.to_image(format="png", width=472, height=h_hist, scale=2)
                img_hist = Image(io.BytesIO(png_hist), width=466, height=h_hist - 6)
                elementos.append(card_wrap(img_hist, w=488))
            except Exception:
                raise RuntimeError("La exportación PNG de Plotly no está disponible; se utilizará el respaldo.")
        elif df_hist is None or df_hist.empty:
            raise RuntimeError("No existen datos históricos para graficar.")
    except Exception:
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates

            df_plot_hist = df_hist.copy() if df_hist is not None else pd.DataFrame()
            if df_plot_hist.empty:
                raise RuntimeError("No existen datos históricos para graficar.")

            df_plot_hist['fecha_corte'] = pd.to_datetime(df_plot_hist['fecha_corte'])
            fig_m, ax_m = plt.subplots(figsize=(7.9, max(2.2, h_hist / 72)), dpi=150)

            for sigla, grupo_hist in df_plot_hist.groupby('sigla', sort=False):
                grupo_hist = grupo_hist.sort_values('fecha_corte')
                ax_m.plot(
                    grupo_hist['fecha_corte'],
                    grupo_hist['monto'],
                    marker='o',
                    linewidth=1.8,
                    markersize=4.5,
                    label=str(sigla)
                )

            ax_m.set_xlabel("")
            ax_m.set_ylabel(f"Monto ({nombre_moneda})", fontsize=8.5)
            ax_m.tick_params(axis='x', labelsize=7.5)
            ax_m.tick_params(axis='y', labelsize=7.5)
            ax_m.grid(True, axis='y', alpha=0.25, linewidth=0.7)
            ax_m.spines['top'].set_visible(False)
            ax_m.spines['right'].set_visible(False)
            ax_m.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
            ax_m.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax_m.get_xticklabels(), rotation=0, ha='center')

            if df_plot_hist['sigla'].nunique() > 0:
                ax_m.legend(
                    fontsize=6.8,
                    loc='upper left',
                    bbox_to_anchor=(1.01, 1),
                    frameon=False
                )

            fig_m.tight_layout(pad=0.8)
            hist_buf = io.BytesIO()
            fig_m.savefig(hist_buf, format='png', transparent=True, bbox_inches='tight', dpi=180)
            plt.close(fig_m)
            hist_buf.seek(0)

            img_hist = Image(hist_buf, width=466, height=h_hist - 6)
            elementos.append(card_wrap(img_hist, w=488))
        except Exception as e_hist:
            elementos.append(
                Paragraph(
                    f"<i>No fue posible renderizar el gráfico histórico: {e_hist}</i>",
                    st_aclaracion
                )
            )

    elementos.append(Spacer(1, 6))

    if ver_hist_tabla and df_hist is not None and not df_hist.empty:
        df_pivot_hist = df_hist.pivot(index='fecha_corte', columns='sigla', values='monto').sort_index(ascending=False)
        df_pivot_hist.index = df_pivot_hist.index.strftime('%Y-%m-%d')
        hist_data_l = [["Fecha"] + list(df_pivot_hist.columns)] + [[str(idx)] + [f"{val:,.2f}" if pd.notnull(val) else "-" for val in row] for idx, row in df_pivot_hist.iterrows()]
        col_w_h = [58] + [float(430 / max(1, len(df_pivot_hist.columns)))] * len(df_pivot_hist.columns)
        t_lam_h = Table(hist_data_l, colWidths=col_w_h)
        t_lam_h.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY_2), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 5.5),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID_LN),
        ]))
        elementos.append(card_wrap(t_lam_h, w=488, pad=0))

    elementos.append(NextPageTemplate('cover'))
    elementos.append(PageBreak())

    # ==========================================
    # LÁMINA 5: DESCARGO Y CIERRE
    # ==========================================
    elementos.append(Chip("INFORMACIÓN INSTITUCIONAL", GOLD, NAVY_2))
    elementos.append(Spacer(1, 10))
    elementos.append(Paragraph("Nota de Descargo", st_titulo_dark))
    elementos.append(Spacer(1, 8))

    descargo_txt = (
        "📌 <b>Nota de Descargo:</b> Los datos mostrados proceden de los Boletines Estadísticos Oficiales "
        "de la ASFI (información pública). Esta información se difunde con fines estrictamente analíticos e "
        "informativos; no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión."
    )
    elementos.append(card_wrap(Paragraph(descargo_txt, st_descargo), w=488, pad=16))
    elementos.append(Spacer(1, 22))

    if LOGO_PATH:
        try:
            logo_cierre = Image(LOGO_PATH, width=150, height=150)
            logo_cierre.hAlign = 'CENTER'
            elementos.append(logo_cierre)
            elementos.append(Spacer(1, 12))
        except Exception:
            pass

    despedida_txt = (
        "<b>¡Gracias por su atención!</b><br/><br/>"
        "Esperamos que este reporte ejecutivo del Sistema Financiero sea de utilidad para la toma de "
        "decisiones estratégicas de su institución.<br/><i>SFB Analytics - Business Intelligence para el Sistema Financiero Boliviano</i>"
    )
    elementos.append(Paragraph(despedida_txt, st_despedida))

    kinds = ['cover', 'content', 'content', 'content', 'cover']

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_footer(num_pages)
                super().showPage()
            super().save()

        def draw_footer(self, page_count):
            idx = self._pageNumber - 1
            kind = kinds[idx] if 0 <= idx < len(kinds) else 'content'
            self.saveState()
            self.setFillColor(MUTED_LT if kind == 'cover' else MUTED)
            self.setFont('Helvetica', 6.8)
            self.drawString(MARGIN, 15, "ASFI · Sistema Financiero Nacional")
            label = f"Lámina {self._pageNumber} / {page_count}"
            chip_w = stringWidth(label, 'Helvetica-Bold', 7.2) + 16
            self.setFillColor(GOLD)
            self.roundRect(PAGE - MARGIN - chip_w, 9, chip_w, 14, 7, fill=1, stroke=0)
            self.setFillColor(NAVY_2)
            self.setFont('Helvetica-Bold', 7.2)
            self.drawCentredString(PAGE - MARGIN - chip_w / 2, 13, label)
            self.restoreState()

    doc.build(elementos, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

def mostrar_reporte_topn_cartera():
    st.markdown("""
        <style>
        .titulo-reporte { font-size: clamp(1.2rem, 2.2vw, 1.8rem) !important; font-weight: 800; margin-top: 0.5rem; margin-bottom: 0.2rem; }
        .subtitulo-reporte { font-size: 0.9rem; margin-bottom: 1rem; }
        .caja-parametros { border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; background-color: #fcfcfc; }
        .leyenda-parametros { font-weight: bold; margin-bottom: 0.5rem; display: block; }
        .grid-donas { display: flex; gap: 20px; width: 100%; }
        .grid-donas > div { flex: 1; min-width: 0; }
        .nota-descargo { font-size: 0.95rem !important; line-height: 1.4; color: #555555; margin-top: 1rem; margin-bottom: 1rem; }
        </style>
    """, unsafe_allow_html=True)

    df_years = consultar_db("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros ORDER BY anio DESC")
    if df_years.empty:
        st.warning("No hay datos disponibles en la base de datos.")
        return

    with st.container():
        st.markdown("<div class='caja-parametros'><span class='leyenda-parametros'>⚙️ Parámetros del Reporte Ejecutivo</span>", unsafe_allow_html=True)
        f1, f2, f3 = st.columns([1, 1, 2])
        anio_sel = f1.selectbox("Año de Corte", df_years['anio'].tolist(), key="a_topn")
        df_fechas = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros WHERE EXTRACT(YEAR FROM fecha_corte) = :anio ORDER BY fecha_corte DESC", {"anio": anio_sel})
        if df_fechas.empty:
            st.warning("No se encontraron fechas de corte para el año seleccionado.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        fecha_sel = f2.selectbox("Fecha de Corte Evaluada", df_fechas['fecha_corte'].astype(str).tolist(), key="f_topn")
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f3.selectbox("📂 Ámbito / Grupo Financiero", ["TOTAL SISTEMA FINANCIERO BOLIVIANO", "TOTAL SISTEMA BANCARIO"] + df_grupos['nombre_grupo'].tolist(), key="g_topn")

        f4, f5, f6 = st.columns([1, 1, 2])
        top_n = f4.number_input("Cantidad de Entidades (Top N)", min_value=1, max_value=30, value=5, step=1, key="n_topn")
        cant_periodos = f5.number_input("Periodos Históricos Atrás", min_value=2, max_value=60, value=12, step=1, key="p_topn")

        dict_indicadores = obtener_indicadores_bcb()
        if "moneda_seleccionada" not in st.session_state or st.session_state.moneda_seleccionada not in dict_indicadores:
            st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]
        st.session_state.moneda_seleccionada = f6.selectbox("💰 Unidad de Medida / Moneda", list(dict_indicadores.keys()), index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada), key="m_topn")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='titulo-reporte'>Reporte Ejecutivo: Análisis Top {top_n} Líderes en Cartera Bruta</div><div class='subtitulo-reporte'>Ámbito: <b>{grupo_sel}</b> | Corte: <b>{fecha_sel}</b> | Histórico: <b>{cant_periodos} periodos</b> | Moneda: <b>{st.session_state.moneda_seleccionada}</b></div>", unsafe_allow_html=True)

    df_total_sis = consultar_db("SELECT SUM(f.monto) as total_bs FROM estados_financieros f JOIN entidades e ON f.entidad = e.nombre_entidad WHERE f.fecha_corte = :fecha AND REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') IN ('13100', '13300', '13400', '13500', '13600', '13700') AND e.nombre_entidad NOT LIKE 'TS%%'", {"fecha": fecha_sel})
    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada]
    nombre_moneda = st.session_state.moneda_seleccionada.split(' ')[0]
    total_sistema_nacional = (df_total_sis['total_bs'].iloc[0] if not df_total_sis.empty and df_total_sis['total_bs'].iloc[0] else 0.0) / factor_conv

    filtro_grupo_sql, params = "", {"fecha": fecha_sel}
    if grupo_sel == "TOTAL SISTEMA BANCARIO":
        filtro_grupo_sql = " AND TRANSLATE(UPPER(g.nombre_grupo), 'ÁÉÍÓÚ', 'AEIOU') IN ('BANCOS MULTIPLES', 'BANCOS PYME', 'BANCOS DE DESARROLLO PRODUCTIVO')"
    elif grupo_sel != "TOTAL SISTEMA FINANCIERO BOLIVIANO":
        filtro_grupo_sql, params["id_grupo"] = " AND g.id_grupo = :id_grupo ", int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

    df_raw = consultar_db(f"""
        SELECT e.nombre_entidad as sigla, COALESCE(NULLIF(e.nombre_completo, ''), e.nombre_entidad) as nombre_completo, g.nombre_grupo, REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') as cod_limpio, f.monto as monto_bs
        FROM estados_financieros f JOIN entidades e ON f.entidad = e.nombre_entidad JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
        WHERE f.fecha_corte = :fecha AND REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') IN ('13100', '13300', '13400', '13500', '13600', '13700') AND e.nombre_entidad NOT LIKE 'TS%%' {filtro_grupo_sql}
    """, params)

    if df_raw.empty:
        st.info("ℹ️ No se encontraron registros de cartera para la combinación seleccionada.")
        return

    df_raw['monto'] = df_raw['monto_bs'] / factor_conv
    df_pivot = df_raw.pivot_table(index=['sigla', 'nombre_completo', 'nombre_grupo'], columns='cod_limpio', values='monto', aggfunc='sum', fill_value=0).reset_index()

    for cod in ['13100', '13300', '13400', '13500', '13600', '13700']:
        if cod not in df_pivot.columns: df_pivot[cod] = 0.0

    df_pivot['Vigente'] = df_pivot['13100'] + df_pivot['13500']
    df_pivot['Vencida'] = df_pivot['13300'] + df_pivot['13600']
    df_pivot['Ejecución'] = df_pivot['13400'] + df_pivot['13700']
    df_pivot['Cartera Bruta'] = df_pivot['Vigente'] + df_pivot['Vencida'] + df_pivot['Ejecución']

    total_cartera_grupo = df_pivot['Cartera Bruta'].sum()
    df_pivot = df_pivot[df_pivot['Cartera Bruta'] > 0].sort_values(by='Cartera Bruta', ascending=False).reset_index(drop=True)
    df_pivot['Posición'] = df_pivot.index + 1
    df_pivot['Participación de Mercado (%)'] = (df_pivot['Cartera Bruta'] / total_cartera_grupo) * 100 if total_cartera_grupo > 0 else 0

    df_topn = df_pivot.head(top_n).copy()
    topn_siglas = df_topn['sigla'].tolist()
    cant_real = len(df_topn)

    # --- SECCIÓN: CONCENTRACIÓN ---
    st.markdown("---")
    st.subheader(f"🍩 Concentración de Cartera: Top {cant_real} vs. Resto")

    monto_topn = df_topn['Cartera Bruta'].sum()
    etiqueta_topn, etiqueta_resto_ambito, etiqueta_resto_sis = f"Top {cant_real} Seleccionado", "Resto del Ámbito", "Resto del Sistema Nacional"
    mapa_colores = {etiqueta_topn: '#004a99', etiqueta_resto_ambito: '#cbd5e1', etiqueta_resto_sis: '#cbd5e1'}
    config_plotly = {'responsive': True, 'displayModeBar': False}

    def crear_fig_pie(titulo, monto_resto, share_resto):
        df_pie = pd.DataFrame([
            {"Entidad / Categoría": etiqueta_topn, "Monto": monto_topn, "Participación de Mercado (%)": (monto_topn / (monto_topn + monto_resto) * 100) if (monto_topn + monto_resto) > 0 else 0},
            {"Entidad / Categoría": titulo, "Monto": monto_resto, "Participación de Mercado (%)": share_resto}
        ])
        fig = px.pie(
            df_pie, names="Entidad / Categoría", values="Monto", hole=0.48, 
            title=f"Concentración en Ámbito:<br><b>{grupo_sel}</b>" if "Ámbito" in titulo else "Concentración en Total:<br><b>SISTEMA FINANCIERO NACIONAL</b>", 
            color="Entidad / Categoría", color_discrete_map=mapa_colores
        )
        fig.update_traces(textinfo='label+percent', textposition='inside', insidetextorientation='tangential')
        fig.update_layout(height=300, margin=dict(l=15, r=15, t=45, b=15), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        return df_pie, fig

    monto_resto_ambito = max(0.0, total_cartera_grupo - monto_topn)
    share_topn_ambito = (monto_topn / total_cartera_grupo * 100) if total_cartera_grupo > 0 else 0
    df_conc_ambito, fig_conc_ambito = crear_fig_pie(etiqueta_resto_ambito, monto_resto_ambito, max(0.0, 100.0 - share_topn_ambito))

    monto_resto_sis = max(0.0, total_sistema_nacional - monto_topn)
    share_topn_sis = (monto_topn / total_sistema_nacional * 100) if total_sistema_nacional > 0 else 0
    _, fig_conc_sis = crear_fig_pie(etiqueta_resto_sis, monto_resto_sis, max(0.0, 100.0 - share_topn_sis))

    st.markdown("<div class='grid-donas'>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: st.plotly_chart(fig_conc_ambito, width="stretch", config=config_plotly)
    with c2: st.plotly_chart(fig_conc_sis, width="stretch", config=config_plotly)
    st.markdown("</div>", unsafe_allow_html=True)

    ver_conc_tabla = st.checkbox(f"📊 Mostrar Tabla de Detalle: Concentración de Cartera (Top {cant_real} vs. Resto)", value=False, key="chk_conc")
    if ver_conc_tabla:
        df_conc_tabla = pd.concat([df_conc_ambito, pd.DataFrame([{"Entidad / Categoría": "TOTAL", "Monto": total_cartera_grupo, "Participación de Mercado (%)": 100.00}])], ignore_index=True)
        df_conc_tabla['Monto'] = df_conc_tabla['Monto'].map('{:,.2f}'.format)
        df_conc_tabla['Participación de Mercado (%)'] = df_conc_tabla['Participación de Mercado (%)'].map('{:.2f}%'.format)
        st.table(df_conc_tabla)

    # --- SECCIÓN: ESTRUCTURA Y COMPOSICIÓN ---
    st.markdown("---")
    st.subheader(f"📊 Estructura de Cartera Bruta - Top {cant_real} ({nombre_moneda})")

    df_topn_bar = df_topn.iloc[::-1].copy()
    df_topn_bar['entidad_etiqueta'] = [f"#{int(pos):02d} - {nom} ({sigla})" for pos, nom, sigla in zip(df_topn_bar['Posición'], df_topn_bar['nombre_completo'], df_topn_bar['sigla'])]

    fig_barras = px.bar(
        df_topn_bar, y='entidad_etiqueta', x=['Vigente', 'Vencida', 'Ejecución'], orientation='h', 
        title=f"Composición por Estado de Cartera (Top {cant_real})", 
        color_discrete_sequence=['#1f77b4', '#d62728', '#ff7f0e'], 
        labels={'value': f'Monto ({nombre_moneda})', 'entidad_etiqueta': '', 'variable': 'Estado'}, 
        custom_data=['Posición', 'nombre_completo', 'sigla', 'nombre_grupo', 'Cartera Bruta', 'Participación de Mercado (%)']
    )
    fig_barras.update_traces(hovertemplate="<b>Puesto #%{customdata[0]}: %{customdata[1]}</b> (%{customdata[2]})<br>Grupo: %{customdata[3]}<br>Estado: %{fullData.name}<br>Monto Estado: %{x:,.2f}<br><b>Cartera Bruta Total: %{customdata[4]:,.2f}</b><br>Participación de Mercado: %{customdata[5]:.2f}%<extra></extra>")
    fig_barras.update_layout(barmode='stack', height=max(280, len(df_topn_bar) * 45), margin=dict(l=280, r=20, t=30, b=25), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(autorange=True, title='', dtick=1), xaxis=dict(title=dict(text=f'Monto ({nombre_moneda})')), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_barras, width="stretch", config=config_plotly)

    ver_topn_tabla = st.checkbox(f"📋 Mostrar Tabla de Detalle: Top {cant_real} a Corte ({fecha_sel})", value=False, key="chk_topn")
    if ver_topn_tabla:
        df_topn_vista = df_topn[['Posición', 'sigla', 'nombre_completo', 'nombre_grupo', 'Vigente', 'Vencida', 'Ejecución', 'Cartera Bruta', 'Participación de Mercado (%)']].rename(columns={'sigla': 'Sigla', 'nombre_completo': 'Nombre Entidad', 'nombre_grupo': 'Grupo / Subgrupo'})
        for col in ['Vigente', 'Vencida', 'Ejecución', 'Cartera Bruta']: df_topn_vista[col] = df_topn_vista[col].map('{:,.2f}'.format)
        df_topn_vista['Participación de Mercado (%)'] = df_topn_vista['Participación de Mercado (%)'].map('{:.2f}%'.format)
        st.table(df_topn_vista)

    # --- SECCIÓN: COMPORTAMIENTO HISTÓRICO ---
    st.markdown("---")
    st.subheader(f"📈 Comportamiento Histórico del Top {cant_real} (Últimos {cant_periodos} Periodos)")

    df_hist, fig_hist = pd.DataFrame(), None
    if topn_siglas:
        df_fechas_limit = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros WHERE fecha_corte <= :fecha_sel ORDER BY fecha_corte DESC LIMIT :cant_periodos", {"fecha_sel": fecha_sel, "cant_periodos": cant_periodos})
        if not df_fechas_limit.empty:
            fechas_validas = df_fechas_limit['fecha_corte'].astype(str).tolist()
            df_hist = consultar_db("SELECT f.fecha_corte, e.nombre_entidad as sigla, SUM(f.monto) as monto_bs FROM estados_financieros f JOIN entidades e ON f.entidad = e.nombre_entidad WHERE e.nombre_entidad IN ({}) AND f.fecha_corte IN ({}) AND REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') IN ('13100', '13300', '13400', '13500', '13600', '13700') GROUP BY f.fecha_corte, e.nombre_entidad ORDER BY f.fecha_corte ASC".format(','.join([f"'{s}'" for s in topn_siglas]), ','.join([f"'{f}'" for f in fechas_validas])))
            if not df_hist.empty:
                df_hist['monto'], df_hist['fecha_corte'] = df_hist['monto_bs'] / factor_conv, pd.to_datetime(df_hist['fecha_corte'])
                fig_hist = px.line(df_hist, x='fecha_corte', y='monto', color='sigla', markers=True, title=f"Tendencia de Cartera Bruta ({cant_periodos} periodos evaluados)", labels={'monto': f'Monto ({nombre_moneda})', 'fecha_corte': 'Fecha de Corte', 'sigla': 'Entidad'}, color_discrete_sequence=px.colors.qualitative.Set2)
                fig_hist.update_layout(height=260, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(title=''), yaxis=dict(title=dict(text=f"Monto ({nombre_moneda})")), margin=dict(l=10, r=30, t=30, b=25))
                st.plotly_chart(fig_hist, width="stretch", config=config_plotly)

    ver_hist_tabla = False
    if not df_hist.empty:
        ver_hist_tabla = st.checkbox(f"📉 Mostrar Tabla de Detalle: Comportamiento Histórico ({cant_periodos} Periodos)", value=False, key="chk_hist")
        if ver_hist_tabla:
            df_pivot_hist = df_hist.pivot(index='fecha_corte', columns='sigla', values='monto').sort_index(ascending=False)
            df_pivot_hist.index = df_pivot_hist.index.strftime('%Y-%m-%d')
            for col in df_pivot_hist.columns: df_pivot_hist[col] = df_pivot_hist[col].map('{:,.2f}'.format)
            st.table(df_pivot_hist)

    st.markdown("---")
    st.markdown(
        "<div class='nota-descargo'>"
        "📌 <b>Nota de Descargo:</b> Los datos mostrados proceden de los Boletines Estadísticos Oficiales de la ASFI (información pública). "
        "Esta información se difunde con fines estrictamente analíticos e informativos; no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión."
        "</div>", 
        unsafe_allow_html=True
    )

    st.markdown("### 📥 Exportar Documento y Presentación")
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        with st.spinner("⏳ Generando reporte PDF vertical tradicional..."):
            pdf_bytes = generar_pdf_reporte(
                df_topn=df_topn, df_conc_ambito=df_conc_ambito, fig_barras=fig_barras, fig_hist=fig_hist, 
                grupo_sel=grupo_sel, fecha_sel=fecha_sel, top_n=top_n, nombre_moneda=nombre_moneda, 
                total_cartera_grupo=total_cartera_grupo, total_sistema_nacional=total_sistema_nacional, 
                ver_conc_tabla=ver_conc_tabla, ver_topn_tabla=ver_topn_tabla, ver_hist_tabla=ver_hist_tabla, 
                cant_periodos=cant_periodos, df_hist=df_hist
            )
        st.download_button(
            label="📄 Descargar Reporte Ejecutivo (PDF)", data=pdf_bytes, 
            file_name=f"Reporte_Cartera_{grupo_sel.replace(' ', '_')}_{fecha_sel}.pdf", 
            mime="application/pdf", key="btn_descargar_pdf"
        )
        
    with col_d2:
        with st.spinner("⏳ Generando presentación en láminas cuadradas con cierre y descargo..."):
            laminas_bytes = generar_pdf_laminas(
                df_topn=df_topn, 
                df_conc_ambito=df_conc_ambito, 
                fig_barras=fig_barras, 
                fig_hist=fig_hist, 
                grupo_sel=grupo_sel, 
                fecha_sel=fecha_sel, 
                top_n=top_n, 
                nombre_moneda=nombre_moneda, 
                total_cartera_grupo=total_cartera_grupo, 
                total_sistema_nacional=total_sistema_nacional, 
                ver_conc_tabla=ver_conc_tabla, 
                ver_topn_tabla=ver_topn_tabla, 
                ver_hist_tabla=ver_hist_tabla, 
                cant_periodos=cant_periodos, 
                df_hist=df_hist
            )
        st.download_button(
            label="📱 Descargar Presentación en Láminas (PDF)", data=laminas_bytes, 
            file_name=f"Laminas_Cartera_{grupo_sel.replace(' ', '_')}_{fecha_sel}.pdf", 
            mime="application/pdf", key="btn_descargar_laminas"
        )

if __name__ == "__main__":
    mostrar_reporte_topn_cartera()