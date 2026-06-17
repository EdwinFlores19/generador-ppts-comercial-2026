import sys
import os
import scraper
import financial_engine
import joule_optimizer

def run_sap_logic_checks():
    print("==================================================")
    print("INICIANDO VALIDACIÓN DE LÓGICA SAP Y JOULE (TDD)")
    print("==================================================")
    
    # ----------------------------------------------------
    # TEST 1: Simulación de 4 Empresas en Distintos Rubros
    # ----------------------------------------------------
    test_companies = [
        {
            "name": "Compañía Minera Las Bambas S.A.",
            "sector": "Minería y Recursos",
            "expected_complexity": "Alta",
            "expected_modules_count": 6  # FI, CO, MM, SD, PP, PS
        },
        {
            "name": "Alicorp S.A.A.",
            "sector": "Alimentos y Agroindustria",
            "expected_complexity": "Alta",
            "expected_modules_count": 6  # FI, CO, MM, SD, PP, PS (Preset)
        },
        {
            "name": "Consultoría Digital Lima S.A.C.",
            "sector": "Servicios Comerciales",
            "expected_complexity": "Media",
            "expected_modules_count": 4  # FI, CO, MM, SD
        },
        {
            "name": "Supermercados Peruanos S.A. (Plaza Vea)",
            "sector": "Retail y Consumo Masivo",
            "expected_complexity": "Alta",
            "expected_modules_count": 6  # FI, CO, MM, SD, PP, PS
        }
    ]
    
    db_config = financial_engine.load_db_config()
    tc = db_config.get('tipo_cambio_pen', 3.78)
    igv_rate = db_config.get('factor_igv', 0.18)
    
    print(f"\n--- Parámetros del Engine: T.C.={tc}, IGV={igv_rate*100}% ---\n")
    
    for idx, company in enumerate(test_companies):
        print(f"Verificando Empresa {idx+1}: {company['name']}...")
        
        # 1. Obtener perfil
        profile = scraper.get_company_profile(company['name'], sector=company['sector'])
        print(f"  > Sector detectado: {profile['sector']}")
        print(f"  > Complejidad: {profile['complexity']} (Esperado: {company['expected_complexity']})")
        
        assert profile['complexity'] == company['expected_complexity'], \
            f"Fallo: Complejidad para {company['name']} debe ser {company['expected_complexity']}."
            
        modules = [m.strip() for m in profile['active_modules'].split(',')]
        assert len(modules) == company['expected_modules_count'], \
            f"Fallo: Cantidad de módulos incorrecta. Esperado {company['expected_modules_count']}, Obtenido {len(modules)}"
            
        # 2. Calcular datos financieros
        fin_data = financial_engine.calculate_financials(modules)
        summary = fin_data['summary']
        
        # 3. Validar Cálculos Matemáticos e IGV en USD
        usd_net = summary['usd']['net_investment']
        usd_igv = summary['usd']['igv']
        usd_total = summary['usd']['total_facturable']
        
        calc_igv_usd = round(usd_net * igv_rate, 2)
        calc_tot_usd = round(usd_net + usd_igv, 2)
        
        print(f"  > USD: Neto={usd_net}, IGV={usd_igv}, Total={usd_total}")
        assert abs(usd_igv - calc_igv_usd) < 0.05, f"Fallo IGV USD: {usd_igv} != {calc_igv_usd}"
        assert abs(usd_total - calc_tot_usd) < 0.05, f"Fallo Total USD: {usd_total} != {calc_tot_usd}"
        
        # 4. Validar Conversión Multimoneda y Cálculos en PEN
        pen_net = summary['pen']['net_investment']
        pen_igv = summary['pen']['igv']
        pen_total = summary['pen']['total_facturable']
        
        calc_net_pen = round(usd_net * tc, 2)
        calc_igv_pen = round(pen_net * igv_rate, 2)
        calc_tot_pen = round(pen_net + pen_igv, 2)
        
        print(f"  > PEN: Neto={pen_net}, IGV={pen_igv}, Total={pen_total}")
        assert abs(pen_net - calc_net_pen) < 0.05, f"Fallo Neto PEN: {pen_net} != {calc_net_pen}"
        assert abs(pen_igv - calc_igv_pen) < 0.05, f"Fallo IGV PEN: {pen_igv} != {calc_igv_pen}"
        assert abs(pen_total - calc_tot_pen) < 0.05, f"Fallo Total PEN: {pen_total} != {calc_tot_pen}"
        
        print(f"  => OK: Empresa {company['name']} validada matemáticamente.\n")
        
    # ----------------------------------------------------
    # TEST 2: Validación de Lógica del Optimizador Joule
    # ----------------------------------------------------
    print("--- Test 2: Validación de Reglas Joule ---")
    
    # Caso 1: Término subjetivo "morosos" -> "facturas vencidas"
    q1 = "Muestra el saldo de los clientes morosos"
    opt1 = joule_optimizer.optimize_prompt(q1)
    print(f"Original:  {q1}\nOptimizado: {opt1['optimized']}")
    assert "facturas vencidas" in opt1['optimized'].lower(), "Fallo: No se tradujo 'morosos'"
    assert "moroso" not in opt1['optimized'].lower(), "Fallo: Se mantuvo el término subjetivo 'morosos'"
    assert opt1['optimized'].startswith("MOSTRAR"), "Fallo: No se asignó palabra mágica MOSTRAR"
    
    # Caso 2: Acción transaccional de creación -> ABRIR
    q2 = "crear una orden de servicio"
    opt2 = joule_optimizer.optimize_prompt(q2)
    print(f"Original:  {q2}\nOptimizado: {opt2['optimized']}")
    assert opt2['optimized'].startswith("ABRIR"), "Fallo: Debería sugerir 'ABRIR'"
    
    # Caso 3: Consulta masiva / agregada con "buscar" -> "MOSTRAR"
    q3 = "buscar contrato de compras con mayor valor"
    opt3 = joule_optimizer.optimize_prompt(q3)
    print(f"Original:  {q3}\nOptimizado: {opt3['optimized']}")
    assert opt3['optimized'].startswith("MOSTRAR"), "Fallo: Debería sugerir 'MOSTRAR' en vez de 'BUSCAR'"
    
    # Caso 4: Buscar facturas pendientes -> LISTAR
    q4 = "buscar las facturas pendientes de clientes"
    opt4 = joule_optimizer.optimize_prompt(q4)
    print(f"Original:  {q4}\nOptimizado: {opt4['optimized']}")
    assert opt4['optimized'].startswith("LISTAR"), "Fallo: Debería sugerir 'LISTAR' en vez de 'BUSCAR'"
    
    # Caso 5: Consulta transaccional de picking con ID
    q5 = "realizar el picking del pedido 80000009"
    opt5 = joule_optimizer.optimize_prompt(q5)
    print(f"Original:  {q5}\nOptimizado: {opt5['optimized']}")
    assert "ABRIR App para Picking" in opt5['optimized'], "Fallo: Debería sugerir ABRIR App de Picking"
    
    print("\n=> OK: Todas las reglas del optimizador de Joule validadas con éxito.")
    
    print("\n==================================================")
    print("¡TESTS DE LÓGICA SAP Y JOULE PASADOS CON ÉXITO!")
    print("==================================================")

if __name__ == "__main__":
    run_sap_logic_checks()
