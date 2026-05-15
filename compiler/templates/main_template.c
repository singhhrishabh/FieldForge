/*
 * FieldForge — ARM Cortex-M0 Firmware Template
 * =============================================
 * Target: STM32F0 series (ARM Cortex-M0, Thumb ISA)
 * Compiler: arm-none-eabi-gcc -mcpu=cortex-m0 -mthumb -Os
 *
 * This template provides:
 *   - Minimal vector table with Reset_Handler
 *   - SystemInit for clock configuration
 *   - GPIO register definitions (GPIOA, GPIOB)
 *   - Basic delay loop
 *   - main() entry point
 *
 * Gemma 4 Architect Agent: Insert your generated logic
 * in the marked sections below.
 */

#include <stdint.h>

/* ─── Register Base Addresses ─────────────────────── */
#define RCC_BASE        0x40021000U
#define GPIOA_BASE      0x48000000U
#define GPIOB_BASE      0x48000400U

/* ─── RCC Registers ───────────────────────────────── */
#define RCC_AHBENR      (*(volatile uint32_t *)(RCC_BASE + 0x14U))
#define RCC_AHBENR_IOPAEN  (1U << 17)  /* GPIOA clock enable */
#define RCC_AHBENR_IOPBEN  (1U << 18)  /* GPIOB clock enable */

/* ─── GPIO Register Offsets ───────────────────────── */
#define GPIO_MODER(base)   (*(volatile uint32_t *)((base) + 0x00U))
#define GPIO_OTYPER(base)  (*(volatile uint32_t *)((base) + 0x04U))
#define GPIO_OSPEEDR(base) (*(volatile uint32_t *)((base) + 0x08U))
#define GPIO_PUPDR(base)   (*(volatile uint32_t *)((base) + 0x0CU))
#define GPIO_IDR(base)     (*(volatile uint32_t *)((base) + 0x10U))
#define GPIO_ODR(base)     (*(volatile uint32_t *)((base) + 0x14U))
#define GPIO_BSRR(base)    (*(volatile uint32_t *)((base) + 0x18U))

/* ─── GPIO Mode Constants ─────────────────────────── */
#define GPIO_MODE_INPUT     0x00U
#define GPIO_MODE_OUTPUT    0x01U
#define GPIO_MODE_ALTFUNC   0x02U
#define GPIO_MODE_ANALOG    0x03U

/* ─── Stack & Entry ───────────────────────────────── */
extern uint32_t _estack;

/* ─── Function Prototypes ─────────────────────────── */
void Reset_Handler(void);
void SystemInit(void);
void Default_Handler(void);
int main(void);

static void delay_ms(volatile uint32_t ms);

/* ─── Vector Table ────────────────────────────────── */
__attribute__((section(".isr_vector")))
const uint32_t vector_table[] = {
    (uint32_t)&_estack,         /* Initial stack pointer */
    (uint32_t)&Reset_Handler,   /* Reset handler */
    (uint32_t)&Default_Handler, /* NMI */
    (uint32_t)&Default_Handler, /* HardFault */
    0, 0, 0, 0, 0, 0, 0,       /* Reserved */
    (uint32_t)&Default_Handler, /* SVCall */
    0, 0,                       /* Reserved */
    (uint32_t)&Default_Handler, /* PendSV */
    (uint32_t)&Default_Handler, /* SysTick */
};

/* ─── Reset Handler ───────────────────────────────── */
void Reset_Handler(void) {
    SystemInit();
    main();
    while (1) {}  /* Never return */
}

/* ─── Default Handler (infinite loop) ─────────────── */
void Default_Handler(void) {
    while (1) {}
}

/* ─── System Init ─────────────────────────────────── */
void SystemInit(void) {
    /* Using default HSI (8 MHz internal oscillator) */
    /* Enable GPIO clocks as needed */
}

/* ─── Delay (approximate, busy-wait) ──────────────── */
static void delay_ms(volatile uint32_t ms) {
    /* ~8000 iterations per ms at 8 MHz HSI */
    volatile uint32_t count;
    while (ms-- > 0) {
        count = 8000;
        while (count-- > 0) {
            __asm__("nop");
        }
    }
}

/* ═══════════════════════════════════════════════════
 *  MAIN — Gemma 4 inserts generated logic here
 * ═══════════════════════════════════════════════════ */
int main(void) {
    /* --- Enable GPIOA clock --- */
    RCC_AHBENR |= RCC_AHBENR_IOPAEN;

    /* --- Configure PA5 as output (LED on Nucleo board) --- */
    GPIO_MODER(GPIOA_BASE) &= ~(0x3U << (5 * 2));  /* Clear mode bits */
    GPIO_MODER(GPIOA_BASE) |=  (GPIO_MODE_OUTPUT << (5 * 2));

    /* --- Main loop: blink LED --- */
    while (1) {
        GPIO_ODR(GPIOA_BASE) ^= (1U << 5);  /* Toggle PA5 */
        delay_ms(500);
    }

    return 0;  /* Never reached */
}
