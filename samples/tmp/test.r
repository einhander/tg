library(shiny)

# Define UI for data upload app ----
ui <- fluidPage(

  # App title ----
  titlePanel("Uploading Files"),

  # Sidebar layout with input and output definitions ----
  sidebarLayout(

    # Sidebar panel for inputs ----
    sidebarPanel(

      # Input: Select a file ----
      fileInput("files", "Upload", multiple = TRUE)
    ),

    # Main panel for displaying outputs ----
    mainPanel(
      # Output: Data file ----
      dataTableOutput("tbl_out")

    )

  )
)

# Define server logic to read selected file ----
server <- function(input, output) {
  lst1 <- reactive({
    validate(need(input$files != "", "select files..."))

    if (is.null(input$files)) {
      return(NULL)
    } else {

      path_list <- as.list(input$files$datapath)
      tbl_list <- lapply(input$files$datapath, read.table, header=FALSE )

      df <- do.call(rbind, tbl_list)
      return(df)
    }
  })

  output$tbl_out <- renderDataTable({
    lst1()
  })

}

# Create Shiny app ----
shinyApp(ui, server)
