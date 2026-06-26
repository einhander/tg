library('mixchar')
library(prospectr)
library('pspline')
library('zoo')
library('pracma')
#library('baseline')
library('ggplot2')

sm <- 25

my_data <- read.csv("Сосна600_10_1800мг.dat", header = FALSE, sep="" )
#my_data <- read.csv("Сосна 600_10_250мг.dat", header = FALSE, sep="" )
#lo <- loess(my_data$V4 ~ my_data$V1)
temp <- movav(my_data$V1,     w=sm)
mass_loss <- movav(my_data$V4,     w=sm)
data <- cbind(temp, mass_loss)

data1 <- tail(data,-10)

data2 <- as.data.frame(data1)

#data2$mass_loss <- data2$mass_loss*1000

deriv_data <- process(data2,                          # dataframe name
                        init_mass = 1.800,
                        temp = 'temp',                 # column name for temperature
                        mass_loss = 'mass_loss')
plot(deriv_data, cex=0.9)

output <- deconvolve(deriv_data)
print(component_weights(output))
plot(output, bw = FALSE)

