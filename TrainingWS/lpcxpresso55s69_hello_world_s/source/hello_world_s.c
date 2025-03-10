/*
 * Copyright 2018 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#if (__ARM_FEATURE_CMSE & 1) == 0
#error "Need ARMv8-M security extensions"
#elif (__ARM_FEATURE_CMSE & 2) == 0
#error "Compile with --cmse"
#endif

#include "fsl_device_registers.h"
#include "fsl_debug_console.h"
#include "arm_cmse.h"
#include "pin_mux.h"
#include "clock_config.h"
#include "board.h"
#include "veneer_table.h"
#include "tzm_config.h"
#include "tzm_api.h"
#include "fsl_gpio.h"

#include "fsl_power.h"
/*******************************************************************************
 * Definitions
 ******************************************************************************/
#define DEMO_CODE_START_NS 0x00010000
#define NON_SECURE_START DEMO_CODE_START_NS

/*******************************************************************************
 * Prototypes
 ******************************************************************************/
//added by Keysight
gpio_pin_config_t PIO0_15_config =
{
   kGPIO_DigitalOutput, // Mode
   0 // Initial State
};

/*******************************************************************************
 * Code
 ******************************************************************************/
/*!
 * @brief Application-specific implementation of the SystemInitHook() weak function.
 */
void SystemInitHook(void)
{
    /* The TrustZone should be configured as early as possible after RESET.
     * Therefore it is called from SystemInit() during startup. The SystemInitHook() weak function
     * overloading is used for this purpose.
     */
	//added by Keysight
    GPIO_PinInit(GPIO, 0, 15, &PIO0_15_config);
    GPIO_PinWrite(GPIO, 0, 15, 0U); // Set pin LOW

    BOARD_InitTrustZone();
}

uint32_t succeeding_fault_targets(void) {
    volatile uint32_t a = 0x000013;

    asm volatile (
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "lsrs %[address], %[address], #1\n\t"  // Logical shift right on the value at the address
        "lsls %[address], %[address], #1\n\t"  // Logical shift left on the value at the address
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        "nop\n"
        : [address]"=r" (a)    // Output operand: modifies the value at the address of `a`
    );
    return a;
}
/*!
 * @brief Main function
 */
int main(void)
{
	volatile uint32_t a = 0x13;
    /* Init board hardware. */
    /* set BOD VBAT level to 1.65V */
    POWER_SetBodVbatLevel(kPOWER_BodVbatLevel1650mv, kPOWER_BodHystLevel50mv, false);
    /* attach main clock divide to FLEXCOMM0 (debug console) */
    CLOCK_AttachClk(BOARD_DEBUG_UART_CLK_ATTACH);

    BOARD_InitPins();
    BOARD_BootClockPLL150M();
    BOARD_InitDebugConsole();
    GPIO_PinWrite(GPIO, 0, 15, 1U); // Set pin HIGH

    a=succeeding_fault_targets();
    GPIO_PinWrite(GPIO, 0, 15, 0U); // Set pin LOW

    PRINTF("%x,%x,%x,%x.",SAU->CTRL,AHB_SECURE_CTRL->MISC_CTRL_REG,AHB_SECURE_CTRL->MISC_CTRL_DP_REG,a);

//    PRINTF("Hello from secure world!\r\n");
//    PRINTF("Entering normal world.\r\n");

    /* Call non-secure application - jump to normal world */
    TZM_JumpToNormalWorld(NON_SECURE_START);

    while (1)
    {
        /* This point should never be reached */
    }
}
