# FIRM firmware for Pinata

This directory contains firmware that implements the target specific part of the *FI Resistance Measure* for the Pinata demo target.

## How to use
1. Download and install [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html)
2. Unpack *firmware.zip*
3. Set up Pinata for flashing via USB (see Pinata Manual for details)
   - Set the *Boot config* switch in the Pinata board to the *SYSTEM* position
   - Set *Power input selector* to *USB*
   - Connect Pinata board via Mini-USB cable
   - Press *Reset* Button on Pinata board
3. Launch *STM32CubeProgrammer*
4. In the right panel, select *USB* as programmer and click *Connect*
5. Make a backup of the factory Pinata firmware:
   - With the *Memory & file editing* tool, in the *Device memory* tab click the *Read* dropdown and select *Save as...*
7. Flash FIRM firmware:
   - Select the *Open File* and select the *pinata_firm.elf* file
   - Click *Download*

## How to roll back to factory Pinata firmware
Follow the same steps as above but use the backup of the Pinata Firmware instead. If you forgot to make a backup, check the [Riscure Support Portal](https://support.riscure.com) to download the latest Pinata Firmware.
