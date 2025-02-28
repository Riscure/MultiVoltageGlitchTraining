/*
 * Copyright 2018 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "fsl_device_registers.h"
#include "fsl_debug_console.h"
#include "veneer_table.h"
#include "pin_mux.h"
#include "clock_config.h"
#include "board.h"
#include "fsl_power.h"
/*******************************************************************************
 * Definitions
 ******************************************************************************/

#define PRINTF_NSE DbgConsole_Printf_NSE
/*******************************************************************************
 * Prototypes
 ******************************************************************************/

/*******************************************************************************
 * Code
 ******************************************************************************/

void SystemInit(void)
{
}
/*!
 * @brief Main function
 */
int main(void)
{
    int result;
    uint32_t *test_ptr;
    volatile uint32_t test_value = 0;

    /* set BOD VBAT level to 1.65V */
    POWER_SetBodVbatLevel(kPOWER_BodVbatLevel1650mv, kPOWER_BodHystLevel50mv, false);

    (void)test_value;
    PRINTF_NSE("Entered ns world");
    test_ptr = (uint32_t *)(0x10000000);//secure code address
    test_value = *test_ptr;

    PRINTF_NSE("Read s world address\r\n");
//    PRINTF_NSE("This is a text printed from normal world!\r\n");
//
//    result = StringCompare_NSE(&strcmp, "Test1\r\n", "Test2\r\n");
//    if (result == 0)
//    {
//        PRINTF_NSE("Both strings are equal!\r\n");
//    }
//    else
//    {
//        PRINTF_NSE("Both strings are not equal!\r\n");
//    }
    while (1)
    {
    }
}
