library('mixchar')
library(prospectr)
library('pspline')
library('zoo')
library('pracma')
#library('baseline')
library('ggplot2')

sm <- 20

my_data <- read.csv("Береза600_10_3140.dat", header = FALSE, sep="" )
#my_data <- read.csv("Сосна 600_10_250мг.dat", header = FALSE, sep="" )
#lo <- loess(my_data$V4 ~ my_data$V1)
temp <- movav(my_data$V1,     w=sm)
mass_loss <- movav(my_data$V4,     w=sm)
data <- cbind(temp, mass_loss)

data1 <- tail(data,-200)

data2 <- as.data.frame(data1)

#data2$mass_loss <- data2$mass_loss*1000

deriv_data <- process(data2,                          # dataframe name
                        init_mass = 3.440,
                        temp = 'temp',                 # column name for temperature
                        mass_loss = 'mass_loss')
plot(deriv_data, cex=0.9, type="l")

my_starting_vec <- c(height_1 = 0.003, skew_1 = -0.15, position_1 = 250, width_1 = 50,
                     height_2 = 0.006, skew_2 = -0.15, position_2 = 320, width_2 = 30,
                     height_3 = 0.001, skew_3 = -0.15, position_3 = 390, width_3 = 200)

output <- deconvolve(deriv_data,  n_peaks = 3, start_vec = my_starting_vec)
print(component_weights(output))
plot(output, bw = FALSE)

