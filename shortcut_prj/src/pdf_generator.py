"""
PDF Generator for Patent Analysis Reports
Using ReportLab for generating professional PDF reports.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from datetime import datetime
from pathlib import Path

# Register Korean Font (Windows default)
FONT_NAME = "Malgun"
try:
    # Windows font path
    font_path = "C:/Windows/Fonts/malgun.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
    else:
        # Fallback if font not found
        FONT_NAME = "Helvetica"
except Exception as e:
    print(f"Font loading error: {e}")
    FONT_NAME = "Helvetica"


class PDFGenerator:
    def __init__(self):
        self.doc = None
        self.elements = []
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Configure custom styles."""
        # Update existing styles with Korean font
        self.styles['Normal'].fontName = FONT_NAME
        self.styles['Heading1'].fontName = FONT_NAME
        self.styles['Heading2'].fontName = FONT_NAME
        self.styles['Heading3'].fontName = FONT_NAME
        self.styles['Code'].fontName = FONT_NAME
        
        # Custom styles
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            leading=30,
            alignment=1,  # Center
            spaceAfter=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            leading=20,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.darkblue,
            borderColor=colors.lightgrey,
            borderPadding=5,
            borderWidth=0,
            borderBottomWidth=1
        ))
        
        self.styles.add(ParagraphStyle(
            name='RiskHigh',
            parent=self.styles['Normal'],
            textColor=colors.red,
            fontName=FONT_NAME,
            fontSize=12,
            leading=14
        ))
        
        self.styles.add(ParagraphStyle(
            name='RiskMedium',
            parent=self.styles['Normal'],
            textColor=colors.orange,
            fontName=FONT_NAME,
            fontSize=12,
            leading=14
        ))

    def generate_report(self, result: dict, filepath: str):
        """Generate PDF report from analysis result."""
        self.doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        self.elements = []
        
        analysis = result.get('analysis', {})
        
        # Title
        self.elements.append(Paragraph("쇼특허 (Short-Cut) 분석 리포트", self.styles['ReportTitle']))
        self.elements.append(Paragraph(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", self.styles['Normal']))
        self.elements.append(Spacer(1, 20))
        
        # User Idea
        self.elements.append(Paragraph("1. 분석 대상 아이디어", self.styles['SectionHeader']))
        self.elements.append(Paragraph(result.get('user_idea', ''), self.styles['Normal']))
        self.elements.append(Spacer(1, 10))
        
        # Conclusion
        self.elements.append(Paragraph("2. 종합 결론", self.styles['SectionHeader']))
        self.elements.append(Paragraph(analysis.get('conclusion', ''), self.styles['Normal']))
        
        # Similarity
        sim = analysis.get('similarity', {})
        self.elements.append(Paragraph("3. 유사도 분석", self.styles['SectionHeader']))
        self.elements.append(Paragraph(f"유사도 점수: {sim.get('score', 0)}/100", self.styles['Heading3']))
        self.elements.append(Paragraph(sim.get('summary', ''), self.styles['Normal']))
        
        # Infringement Risk
        inf = analysis.get('infringement', {})
        risk = inf.get('risk_level', 'unknown').upper()
        self.elements.append(Paragraph("4. 침해 리스크", self.styles['SectionHeader']))
        
        risk_style = self.styles['Normal']
        if risk == 'HIGH': risk_style = self.styles['RiskHigh']
        elif risk == 'MEDIUM': risk_style = self.styles['RiskMedium']
        
        self.elements.append(Paragraph(f"리스크 수준: {risk}", risk_style))
        self.elements.append(Paragraph(inf.get('summary', ''), self.styles['Normal']))
        
        # Evidence Table
        self.elements.append(Paragraph("5. 주요 유사 특허", self.styles['SectionHeader']))
        
        data = [['특허번호', '제목', '관련성 점수']]
        for r in result.get('search_results', [])[:5]:
            data.append([
                r.get('patent_id', ''),
                Paragraph(r.get('title', '')[:30] + '...', self.styles['Normal']),
                f"{r.get('grading_score', 0):.2f}"
            ])
            
        t = Table(data, colWidths=[2.5*inch, 3.5*inch, 1*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        self.elements.append(t)
        
        # Build PDF
        self.doc.build(self.elements)
        return filepath
